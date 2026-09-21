"""Optional PyVISA-backed byte transport.

PyVISA may return the same ResourceManager object for every caller using one
VISA library. Consequently this transport always treats a manager as borrowed:
closing one transport closes only its resource, never the process-wide manager.
"""

from __future__ import annotations

import importlib
from contextlib import suppress
from types import ModuleType
from typing import Any, Final

from scpi_driver_core.exceptions import (
    ConfigurationError,
    NotConnectedError,
    TransportError,
    TransportTimeoutError,
    UnsupportedOperationError,
)
from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)
from scpi_driver_core.transport.socket_utils import effective_timeout, validate_timeout
from scpi_driver_core.transport.state import TransportStateMachine

__all__ = ["VisaTransport"]

_VI_ERROR_TMO: Final = -1073807339
_DEFAULT_CHUNK_SIZE: Final = 20 * 1024


def _load_pyvisa() -> ModuleType:
    try:
        return importlib.import_module("pyvisa")
    except ImportError as exc:
        raise ConfigurationError(
            "VisaTransport requires PyVISA; install scpi-driver-core[visa]"
        ) from exc


def _load_constants() -> ModuleType | None:
    try:
        return importlib.import_module("pyvisa.constants")
    except ImportError:
        return None


def _is_timeout(exc: BaseException) -> bool:
    return getattr(exc, "error_code", None) == _VI_ERROR_TMO


def _translate(exc: BaseException, action: str) -> TransportError:
    if _is_timeout(exc):
        return TransportTimeoutError(f"VISA {action} timed out")
    return TransportError(f"VISA {action} failed: {exc}")


class VisaTransport(TransportStateMachine):
    """A byte-preserving VISA session.

    GPIB, USBTMC and ``TCPIP::INSTR`` sessions have a backend END boundary and
    can use ``BACKEND_DEFINED_MESSAGE``. ASRL and ``TCPIP::SOCKET`` are byte
    streams and still require explicit text framing/termination appropriate to
    the selected VISA implementation.
    """

    def __init__(
        self,
        resource_name: str,
        *,
        timeout_s: float = 5.0,
        resource_manager: Any | None = None,
        visa_library: str = "",
        chunk_size: int = _DEFAULT_CHUNK_SIZE,
    ) -> None:
        if not resource_name:
            raise ConfigurationError("resource_name must not be empty")
        validate_timeout(timeout_s, "timeout_s")
        if chunk_size <= 0:
            raise ConfigurationError(f"chunk_size must be positive, got {chunk_size!r}")
        self._resource_name = resource_name
        self._timeout_s = timeout_s
        self._external_manager = resource_manager
        self._visa_library = visa_library
        self._chunk_size = chunk_size
        self._resource: Any | None = None
        self._buffer = bytearray()
        metadata = {"visa_library": visa_library} if visa_library else {}
        super().__init__(TransportDescriptor(kind="visa", address=resource_name, metadata=metadata))

    @property
    def message_based(self) -> bool:
        """Whether this VISA address has a hardware/backend END message boundary."""
        name = self._resource_name.upper()
        return name.endswith("::INSTR") and not name.startswith("ASRL")

    def open(self) -> TransportDescriptor:
        with self._lock:
            if self.state is TransportState.OPEN:
                return self._descriptor
            borrowed = self._external_manager
            pyvisa = _load_pyvisa() if borrowed is None else None
            self._release_resource()
            self._set_state(TransportState.OPENING)
            self._buffer.clear()
            resource: Any | None = None
            try:
                if borrowed is not None:
                    manager = borrowed
                else:
                    assert pyvisa is not None
                    # ResourceManager is a per-library singleton in PyVISA. It is
                    # borrowed even though this call obtained the reference.
                    manager = pyvisa.ResourceManager(self._visa_library)
                resource = manager.open_resource(
                    self._resource_name,
                    read_termination=None,
                    write_termination=None,
                )
                resource.timeout = self._timeout_s * 1000.0
                resource.chunk_size = self._chunk_size
            except Exception as exc:
                if resource is not None:
                    self._safely_close(resource)
                self._set_state(TransportState.FAULTED)
                raise _translate(exc, f"open of {self._resource_name}") from exc
            self._resource = resource
            self._set_state(TransportState.OPEN)
            return self._descriptor

    @staticmethod
    def _apply_timeout(resource: Any, timeout_ms: float) -> None:
        if resource.timeout != timeout_ms:
            resource.timeout = timeout_ms

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        del operation_id
        timeout = effective_timeout(timeout_s, self._timeout_s)
        with self._lock:
            resource = self._require_open()
            sent = 0
            with self._faulting_io():
                try:
                    self._apply_timeout(resource, timeout * 1000.0)
                    while sent < len(data):
                        count = resource.write_raw(data[sent:])
                        written = len(data) - sent if count is None else int(count)
                        if written <= 0:
                            raise TransportTimeoutError("VISA write made no progress")
                        sent += written
                except Exception as exc:
                    if isinstance(exc, TransportError):
                        raise
                    raise _translate(exc, "write") from exc
            return WriteResult(bytes_written=sent)

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes:
        del operation_id
        timeout = effective_timeout(timeout_s, self._timeout_s)
        with self._lock:
            resource = self._require_open()
            with self._faulting_io():
                try:
                    self._apply_timeout(resource, timeout * 1000.0)
                    return self._read(resource, request)
                except Exception as exc:
                    if isinstance(exc, TransportError):
                        raise
                    raise _translate(exc, "read") from exc

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes:
        del replay_policy
        with self._lock, self._faulting_io():
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        """Discard local/VISA buffers without sending Device Clear."""
        with self._lock:
            resource = self._require_open()
            if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                self._buffer.clear()
                self._try_discard_masks(resource, input_side=True)
            if direction in (FlushDirection.OUTPUT, FlushDirection.BOTH):
                self._try_discard_masks(resource, input_side=False)

    def _try_discard_masks(self, resource: Any, *, input_side: bool) -> None:
        constants = _load_constants()
        flush = getattr(resource, "flush", None)
        if constants is None or not callable(flush):
            return
        ops = constants.BufferOperation
        masks: tuple[Any, ...]
        if input_side:
            masks = (
                ops.discard_read_buffer_no_io | ops.discard_receive_buffer,
                ops.discard_read_buffer_no_io,
            )
        else:
            masks = (ops.discard_write_buffer,)
        for mask in masks:
            try:
                flush(mask)
                return
            except Exception:
                continue
        # Deliberately degrade to local-only discard. viClear is not a flush.

    # -- explicit IEEE-488/VISA capabilities -----------------------------

    def device_clear(self) -> None:
        """Issue ``viClear`` explicitly; this may abort instrument activity."""
        with self._lock:
            resource = self._require_open()
            with self._faulting_io():
                self._buffer.clear()
                try:
                    resource.clear()
                except Exception as exc:
                    raise _translate(exc, "device clear") from exc

    def read_status_byte(self, *, timeout_s: float | None = None) -> int:
        with self._lock:
            resource = self._require_open()
            timeout = effective_timeout(timeout_s, self._timeout_s)
            with self._faulting_io():
                try:
                    self._apply_timeout(resource, timeout * 1000.0)
                    return int(resource.read_stb())
                except Exception as exc:
                    raise _translate(exc, "serial poll") from exc

    def assert_trigger(self) -> None:
        with self._lock:
            resource = self._require_open()
            with self._faulting_io():
                try:
                    resource.assert_trigger()
                except Exception as exc:
                    raise _translate(exc, "bus trigger") from exc

    def go_to_local(self) -> None:
        with self._lock:
            resource = self._require_open()
            constants = _load_constants()
            if constants is None or not hasattr(resource, "control_ren"):
                raise UnsupportedOperationError("VISA backend does not expose local control")
            with self._faulting_io():
                try:
                    resource.control_ren(constants.RENLineOperation.deassert_gtl)
                except Exception as exc:
                    raise _translate(exc, "go to local") from exc

    # -- read modes -------------------------------------------------------

    def _read(self, resource: Any, request: ReadRequest) -> bytes:
        if request.mode is ReadMode.BACKEND_DEFINED_MESSAGE:
            if not self.message_based:
                raise UnsupportedOperationError(
                    f"{self._resource_name} has no reliable VISA END message boundary"
                )
            if self._buffer:
                return self._take(min(len(self._buffer), request.maximum_size))
            return self._read_message_bounded(resource, request.maximum_size)

        if request.mode is ReadMode.EXACT_LENGTH:
            assert request.length is not None
            while len(self._buffer) < request.length:
                chunk = bytes(resource.read_bytes(request.length - len(self._buffer)))
                if not chunk:
                    raise TransportTimeoutError("VISA exact-length read made no progress")
                self._buffer.extend(chunk)
            return self._take(request.length)

        if request.mode is ReadMode.UNTIL_TERMINATOR:
            assert request.terminator is not None
            search_from = 0
            while True:
                index = self._buffer.find(request.terminator, search_from)
                if index >= 0:
                    end = index + len(request.terminator)
                    if end > request.maximum_size:
                        raise TransportError(
                            f"message of {end} bytes exceeds maximum_size {request.maximum_size}"
                        )
                    data = self._take(end)
                    return data if request.include_terminator else data[: -len(request.terminator)]
                if len(self._buffer) >= request.maximum_size:
                    raise TransportError(
                        f"no terminator within maximum_size {request.maximum_size}"
                    )
                search_from = max(0, len(self._buffer) - len(request.terminator) + 1)
                remaining = request.maximum_size - len(self._buffer)
                self._buffer.extend(self._read_message_bounded(resource, remaining))

        limit = request.maximum_size
        if request.mode is ReadMode.UP_TO_LENGTH:
            assert request.length is not None
            limit = min(request.length, limit)
        if not self._buffer:
            self._buffer.extend(self._read_at_most(resource, limit))
        return self._take(min(len(self._buffer), limit))

    def _read_at_most(self, resource: Any, maximum_size: int) -> bytes:
        """Read one bounded chunk/message fragment, waiting for at least one byte."""
        if maximum_size <= 0:
            return b""
        visalib = getattr(resource, "visalib", None)
        session = getattr(resource, "session", None)
        if visalib is not None and session is not None:
            data, _status = visalib.read(session, min(self._chunk_size, maximum_size))
            return bytes(data)
        # Test doubles and unusual wrappers may not expose the low-level handle.
        data = bytes(resource.read_raw())
        if len(data) > maximum_size:
            raise TransportError(f"VISA read exceeds maximum_size {maximum_size}")
        return data

    def _read_message_bounded(self, resource: Any, maximum_size: int) -> bytes:
        """Read through the VISA low-level API so total allocation is bounded."""
        visalib = getattr(resource, "visalib", None)
        session = getattr(resource, "session", None)
        constants = _load_constants()
        if visalib is None or session is None or constants is None:
            data = bytes(resource.read_raw())
            if len(data) > maximum_size:
                raise TransportError(
                    f"message of {len(data)} bytes exceeds maximum_size {maximum_size}"
                )
            return data

        out = bytearray()
        max_count_status = constants.StatusCode.success_max_count_read
        while True:
            want = min(self._chunk_size, maximum_size + 1 - len(out))
            if want <= 0:
                raise TransportError(f"VISA message exceeds maximum_size {maximum_size}")
            chunk, status = visalib.read(session, want)
            out.extend(chunk)
            if len(out) > maximum_size:
                raise TransportError(f"VISA message exceeds maximum_size {maximum_size}")
            if status != max_count_status:
                return bytes(out)

    def _take(self, count: int) -> bytes:
        data = bytes(memoryview(self._buffer)[:count])
        del self._buffer[:count]
        return data

    def _require_open(self) -> Any:
        self._require_state_open()
        if self._resource is None:
            raise NotConnectedError("transport is OPEN but holds no resource")
        return self._resource

    def _on_closed(self) -> None:
        self._buffer.clear()

    def _release_resource(self) -> None:
        resource, self._resource = self._resource, None
        if resource is not None:
            self._safely_close(resource)
        # Never close ResourceManager: PyVISA shares it process-wide per library.

    @staticmethod
    def _safely_close(target: Any) -> None:
        with suppress(Exception):
            target.close()
