"""Optional pyserial-backed byte transport."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Any

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

__all__ = ["SerialTransport"]


def _load_serial() -> ModuleType:
    try:
        return importlib.import_module("serial")
    except ImportError as exc:
        raise ConfigurationError(
            "SerialTransport requires pyserial; install scpi-driver-core[serial]"
        ) from exc


class SerialTransport(TransportStateMachine):
    """A finite-timeout serial stream with explicit line/flow-control policy."""

    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 9600,
        timeout_s: float = 5.0,
        write_timeout_s: float = 5.0,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        dtr: bool | None = None,
        rts: bool | None = None,
        rtscts: bool = False,
        dsrdtr: bool = False,
        xonxoff: bool = False,
        exclusive: bool | None = None,
    ) -> None:
        if not port:
            raise ConfigurationError("port must not be empty")
        if baudrate <= 0:
            raise ConfigurationError("baudrate must be positive")
        validate_timeout(timeout_s, "timeout_s")
        validate_timeout(write_timeout_s, "write_timeout_s")
        if bytesize not in (5, 6, 7, 8):
            raise ConfigurationError("bytesize must be one of 5, 6, 7, or 8")
        if parity.upper() not in ("N", "E", "O", "M", "S"):
            raise ConfigurationError("parity must be N, E, O, M, or S")
        if stopbits not in (1, 1.5, 2):
            raise ConfigurationError("stopbits must be 1, 1.5, or 2")

        self._port = port
        self._baudrate = baudrate
        self._timeout_s = timeout_s
        self._write_timeout_s = write_timeout_s
        self._bytesize = bytesize
        self._parity = parity.upper()
        self._stopbits = stopbits
        self._dtr = dtr
        self._rts = rts
        self._rtscts = rtscts
        self._dsrdtr = dsrdtr
        self._xonxoff = xonxoff
        self._exclusive = exclusive
        self._resource: Any | None = None
        super().__init__(
            TransportDescriptor(
                kind="serial",
                address=port,
                metadata={
                    "baudrate": str(baudrate),
                    "parity": self._parity,
                    "rtscts": str(rtscts),
                    "dsrdtr": str(dsrdtr),
                    "xonxoff": str(xonxoff),
                },
            )
        )

    def open(self) -> TransportDescriptor:
        with self._lock:
            if self.state is TransportState.OPEN:
                return self._descriptor
            serial = _load_serial()
            self._release_resource()
            self._set_state(TransportState.OPENING)
            resource: Any | None = None
            try:
                factory = getattr(serial, "serial_for_url", None)
                if callable(factory):
                    resource = factory(self._port, do_not_open=True)
                    resource.baudrate = self._baudrate
                    resource.timeout = self._timeout_s
                    resource.write_timeout = self._write_timeout_s
                    resource.bytesize = self._bytesize
                    resource.parity = self._parity
                    resource.stopbits = self._stopbits
                    resource.rtscts = self._rtscts
                    resource.dsrdtr = self._dsrdtr
                    resource.xonxoff = self._xonxoff
                    if self._dtr is not None:
                        resource.dtr = self._dtr
                    if self._rts is not None:
                        resource.rts = self._rts
                    if self._exclusive is not None and hasattr(resource, "exclusive"):
                        resource.exclusive = self._exclusive
                    resource.open()
                else:  # lightweight fake backends used by downstream tests
                    resource = serial.Serial(
                        port=self._port,
                        baudrate=self._baudrate,
                        timeout=self._timeout_s,
                        write_timeout=self._write_timeout_s,
                        bytesize=self._bytesize,
                        parity=self._parity,
                        stopbits=self._stopbits,
                        rtscts=self._rtscts,
                        dsrdtr=self._dsrdtr,
                        xonxoff=self._xonxoff,
                    )
                    if self._dtr is not None:
                        resource.dtr = self._dtr
                    if self._rts is not None:
                        resource.rts = self._rts
                    if self._exclusive is not None and hasattr(resource, "exclusive"):
                        resource.exclusive = self._exclusive
            except Exception as exc:
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        pass
                self._set_state(TransportState.FAULTED)
                raise TransportError(f"serial open failed for {self._port}: {exc}") from exc
            self._resource = resource
            self._set_state(TransportState.OPEN)
            return self._descriptor

    @staticmethod
    def _apply_timeouts(
        resource: Any,
        *,
        read: float | None = None,
        write: float | None = None,
    ) -> None:
        if read is not None and resource.timeout != read:
            resource.timeout = read
        if write is not None and resource.write_timeout != write:
            resource.write_timeout = write

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        del operation_id
        timeout = effective_timeout(timeout_s, self._write_timeout_s)
        with self._lock:
            resource = self._require_open()
            sent = 0
            with self._faulting_io():
                try:
                    self._apply_timeouts(resource, write=timeout)
                    while sent < len(data):
                        count = int(resource.write(data[sent:]))
                        if count <= 0:
                            raise TransportTimeoutError("serial write made no progress")
                        sent += count
                except Exception as exc:
                    if isinstance(exc, TransportError):
                        raise
                    if exc.__class__.__name__ == "SerialTimeoutException":
                        raise TransportTimeoutError("serial write timed out") from exc
                    raise TransportError(f"serial write failed: {exc}") from exc
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
            if request.mode is ReadMode.BACKEND_DEFINED_MESSAGE:
                raise UnsupportedOperationError(
                    "serial is a byte stream without message boundaries"
                )
            with self._faulting_io():
                try:
                    self._apply_timeouts(resource, read=timeout)
                    return self._read(resource, request)
                except Exception as exc:
                    if isinstance(exc, TransportError):
                        raise
                    raise TransportError(f"serial read failed: {exc}") from exc

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
        with self._lock:
            resource = self._require_open()
            with self._faulting_io():
                try:
                    if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                        resource.reset_input_buffer()
                    if direction in (FlushDirection.OUTPUT, FlushDirection.BOTH):
                        resource.reset_output_buffer()
                except Exception as exc:
                    raise TransportError(f"serial flush failed: {exc}") from exc

    def _read(self, resource: Any, request: ReadRequest) -> bytes:
        if request.mode is ReadMode.EXACT_LENGTH:
            assert request.length is not None
            data = bytes(resource.read(request.length))
            if len(data) != request.length:
                raise TransportTimeoutError(
                    f"serial read returned {len(data)} of {request.length} bytes before timeout"
                )
            return data

        if request.mode is ReadMode.UNTIL_TERMINATOR:
            assert request.terminator is not None
            data = bytes(resource.read_until(request.terminator, request.maximum_size))
            if not data.endswith(request.terminator):
                if len(data) >= request.maximum_size:
                    raise TransportError("terminator not found before maximum_size")
                raise TransportTimeoutError("serial terminated read timed out")
            return data if request.include_terminator else data[: -len(request.terminator)]

        if request.mode is ReadMode.UP_TO_LENGTH:
            assert request.length is not None
            limit = min(request.length, request.maximum_size)
        else:
            limit = request.maximum_size

        first = bytes(resource.read(1))
        if not first:
            raise TransportTimeoutError("serial read timed out")
        waiting = min(int(resource.in_waiting), limit - 1)
        return first + (bytes(resource.read(waiting)) if waiting else b"")

    def _require_open(self) -> Any:
        self._require_state_open()
        if self._resource is None:
            raise NotConnectedError("transport is OPEN but holds no resource")
        return self._resource

    def _release_resource(self) -> None:
        resource, self._resource = self._resource, None
        if resource is not None:
            resource.close()
