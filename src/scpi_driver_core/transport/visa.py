"""Optional PyVISA-backed byte transport.

VISA is the only backend here with native message boundaries, so it is the one
that implements :attr:`ReadMode.BACKEND_DEFINED_MESSAGE` by reading exactly one
VISA message rather than refusing.

Byte fidelity is the overriding concern. The resource is always opened with
both terminations disabled and driven through ``write_raw``/``read_bytes``, so
PyVISA never encodes, decodes, appends, or trims anything. SCPI framing is the
codec's job, one layer up.
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

#: VI_ERROR_TMO. Matched numerically so the module never imports PyVISA merely
#: to classify an exception.
_VI_ERROR_TMO: Final = -1073807339

_DEFAULT_CHUNK_SIZE: Final = 20 * 1024


def _load_pyvisa() -> ModuleType:
    try:
        return importlib.import_module("pyvisa")
    except ImportError as exc:
        raise ConfigurationError(
            "VisaTransport requires PyVISA; install scpi-driver-core[visa]"
        ) from exc


def _is_timeout(exc: BaseException) -> bool:
    return getattr(exc, "error_code", None) == _VI_ERROR_TMO


def _translate(exc: BaseException, action: str) -> TransportError:
    if _is_timeout(exc):
        return TransportTimeoutError(f"VISA {action} timed out")
    return TransportError(f"VISA {action} failed: {exc}")


class VisaTransport(TransportStateMachine):
    """A byte-preserving VISA session.

    Works with any resource class the underlying VISA library supports,
    including ``GPIB``, ``USB`` (USBTMC), ``TCPIP::INSTR``, ``TCPIP::SOCKET``
    and ``ASRL``. Nothing here is specific to a resource class; the address is
    passed through untouched.

    The constructor performs no I/O: it neither opens the resource nor queries
    the instrument, and it never enumerates the VISA registry. A mistyped
    resource name surfaces at :meth:`open`, not at import or construction.

    Args:
        resource_name: a VISA resource string, such as ``GPIB0::22::INSTR``.
        timeout_s: default bound for operations. PyVISA works in milliseconds;
            the conversion happens here so callers stay in seconds.
        resource_manager: an existing ``pyvisa.ResourceManager`` to borrow. When
            given, it is never closed by this transport, since its lifetime
            belongs to whoever created it. When omitted, one is created on
            :meth:`open` and closed deterministically on :meth:`close`.
        visa_library: passed to ``ResourceManager`` when creating one, for
            example ``"@py"`` for pyvisa-py. Ignored if ``resource_manager`` is
            supplied.
        chunk_size: how much to request per underlying read.

    Raises:
        ConfigurationError: if the resource name is empty, the timeout is not
            finite and positive, or PyVISA is not installed when opening.
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

        metadata = {"visa_library": visa_library} if visa_library else {}
        super().__init__(TransportDescriptor(kind="visa", address=resource_name, metadata=metadata))
        self._resource: Any | None = None
        self._owned_manager: Any | None = None
        self._buffer = bytearray()

    # -- lifecycle --------------------------------------------------------

    def open(self) -> TransportDescriptor:
        """Acquire the VISA session, releasing any previously failed one first."""
        with self._lock:
            if self._state is TransportState.OPEN:
                return self._descriptor

            # Resolve the backend before touching any state, so a missing
            # PyVISA leaves the transport exactly as it was.
            borrowed = self._external_manager
            pyvisa = _load_pyvisa() if borrowed is None else None

            self._release_resource()
            self._state = TransportState.OPENING
            self._buffer.clear()

            resource: Any | None = None
            try:
                if borrowed is not None:
                    manager = borrowed
                else:
                    assert pyvisa is not None  # set whenever borrowed is None
                    manager = pyvisa.ResourceManager(self._visa_library)
                    self._owned_manager = manager
                resource = manager.open_resource(
                    self._resource_name,
                    # Terminations must stay off: PyVISA would otherwise trim or
                    # append bytes, which would corrupt binary block transfers.
                    read_termination=None,
                    write_termination=None,
                )
                resource.timeout = self._timeout_s * 1000.0
                resource.chunk_size = self._chunk_size
            except Exception as exc:
                if resource is not None:
                    self._safely_close(resource)
                self._release_manager()
                self._state = TransportState.FAULTED
                raise _translate(exc, f"open of {self._resource_name}") from exc

            self._resource = resource
            self._state = TransportState.OPEN
            return self._descriptor

    # -- I/O --------------------------------------------------------------

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        """Send ``data`` verbatim through ``write_raw``."""
        del operation_id
        timeout = effective_timeout(timeout_s, self._timeout_s)
        with self._lock:
            resource = self._require_open()
            try:
                resource.timeout = timeout * 1000.0
                sent = 0
                while sent < len(data):
                    count = resource.write_raw(data[sent:])
                    # PyVISA backends may report None rather than a count.
                    written = len(data) - sent if count is None else int(count)
                    if written <= 0:
                        raise TransportTimeoutError("VISA write made no progress")
                    sent += written
            except Exception as exc:
                self._fault()
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
        """Read according to ``request``, buffering whole VISA messages."""
        del operation_id
        timeout = effective_timeout(timeout_s, self._timeout_s)
        with self._lock:
            resource = self._require_open()
            try:
                resource.timeout = timeout * 1000.0
                return self._read(resource, request)
            except Exception as exc:
                self._fault()
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
        """Write then read while holding the lock across both halves.

        ``replay_policy`` is accepted for contract compatibility and ignored:
        VISA sessions are reliable, so there is nothing to retransmit.
        """
        del replay_policy
        with self._lock:
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        """Discard buffered input.

        VISA exposes only a whole-session ``clear``, so an output-only flush
        drops nothing rather than pretending to be selective.
        """
        with self._lock:
            resource = self._require_open()
            if direction is FlushDirection.OUTPUT:
                return
            try:
                self._buffer.clear()
                resource.clear()
            except Exception as exc:
                self._fault()
                raise _translate(exc, "flush") from exc

    # -- read modes -------------------------------------------------------

    def _read(self, resource: Any, request: ReadRequest) -> bytes:
        if request.mode is ReadMode.BACKEND_DEFINED_MESSAGE:
            if self._buffer:
                return self._take(min(len(self._buffer), request.maximum_size))
            message = bytes(resource.read_raw())
            if len(message) > request.maximum_size:
                raise TransportError(
                    f"message of {len(message)} bytes exceeds maximum_size {request.maximum_size}"
                )
            return message

        if request.mode is ReadMode.EXACT_LENGTH:
            length = request.length
            assert length is not None  # guaranteed by ReadRequest validation
            while len(self._buffer) < length:
                self._buffer.extend(resource.read_bytes(length - len(self._buffer)))
            return self._take(length)

        if request.mode is ReadMode.UNTIL_TERMINATOR:
            terminator = request.terminator
            assert terminator is not None  # guaranteed by ReadRequest validation
            while True:
                index = self._buffer.find(terminator)
                if index >= 0:
                    break
                if len(self._buffer) >= request.maximum_size:
                    raise TransportError(
                        f"no terminator within maximum_size {request.maximum_size}"
                    )
                self._buffer.extend(resource.read_raw())
            end = index + len(terminator)
            if end > request.maximum_size:
                raise TransportError(
                    f"message of {end} bytes exceeds maximum_size {request.maximum_size}"
                )
            data = self._take(end)
            return data if request.include_terminator else data[: -len(terminator)]

        # UP_TO_LENGTH and AVAILABLE both return whatever has arrived. VISA
        # cannot report "nothing waiting" without waiting, so when the buffer is
        # empty these read one message, bounded by the timeout.
        limit = request.maximum_size
        if request.mode is ReadMode.UP_TO_LENGTH:
            length = request.length
            assert length is not None  # guaranteed by ReadRequest validation
            limit = min(length, limit)
        if not self._buffer:
            self._buffer.extend(resource.read_raw())
        return self._take(min(len(self._buffer), limit))

    # -- internals --------------------------------------------------------

    def _take(self, count: int) -> bytes:
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data

    def _require_open(self) -> Any:
        self._require_state_open()
        if self._resource is None:  # pragma: no cover - OPEN implies a resource
            raise NotConnectedError("transport is OPEN but holds no resource")
        return self._resource

    def _on_closed(self) -> None:
        self._buffer.clear()

    def _release_resource(self) -> None:
        resource, self._resource = self._resource, None
        if resource is not None:
            self._safely_close(resource)
        self._release_manager()

    def _release_manager(self) -> None:
        manager, self._owned_manager = self._owned_manager, None
        if manager is not None:
            self._safely_close(manager)

    @staticmethod
    def _safely_close(target: Any) -> None:
        """Close without masking the failure that led here."""
        with suppress(Exception):
            target.close()
