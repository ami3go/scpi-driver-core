"""Optional pyserial-backed byte transport."""

from __future__ import annotations

import importlib
import threading
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

__all__ = ["SerialTransport"]


def _load_serial() -> ModuleType:
    try:
        return importlib.import_module("serial")
    except ImportError as exc:
        raise ConfigurationError(
            "SerialTransport requires pyserial; install scpi-driver-core[serial]"
        ) from exc


class SerialTransport:
    """A finite-timeout serial byte stream with no implicit SCPI framing."""

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
        self._descriptor = TransportDescriptor(
            kind="serial",
            address=port,
            metadata={"baudrate": str(baudrate), "parity": self._parity},
        )
        self._state = TransportState.CREATED
        self._resource: Any | None = None
        self._lock = threading.RLock()

    @property
    def state(self) -> TransportState:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state is TransportState.OPEN

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._descriptor

    def open(self) -> TransportDescriptor:
        with self._lock:
            if self._state is TransportState.OPEN:
                return self._descriptor
            serial = _load_serial()
            self._release()
            self._state = TransportState.OPENING
            resource: Any | None = None
            try:
                resource = serial.Serial(
                    port=self._port,
                    baudrate=self._baudrate,
                    timeout=self._timeout_s,
                    write_timeout=self._write_timeout_s,
                    bytesize=self._bytesize,
                    parity=self._parity,
                    stopbits=self._stopbits,
                )
                if self._dtr is not None:
                    resource.dtr = self._dtr
                if self._rts is not None:
                    resource.rts = self._rts
            except Exception as exc:
                if resource is not None:
                    resource.close()
                self._state = TransportState.FAULTED
                raise TransportError(f"serial open failed for {self._port}: {exc}") from exc
            self._resource = resource
            self._state = TransportState.OPEN
            return self._descriptor

    def close(self) -> None:
        with self._lock:
            if self._state in (TransportState.CREATED, TransportState.CLOSED):
                return
            self._state = TransportState.CLOSING
            self._release()
            self._state = TransportState.CLOSED

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
            try:
                resource.write_timeout = timeout
                while sent < len(data):
                    count = int(resource.write(data[sent:]))
                    if count <= 0:
                        raise TransportTimeoutError("serial write made no progress")
                    sent += count
            except Exception as exc:
                self._fault()
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
            try:
                resource.timeout = timeout
                data = self._read(resource, request)
            except Exception as exc:
                self._fault()
                if isinstance(exc, TransportError):
                    raise
                raise TransportError(f"serial read failed: {exc}") from exc
            return data

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
        with self._lock:
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        with self._lock:
            resource = self._require_open()
            try:
                if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                    resource.reset_input_buffer()
                if direction in (FlushDirection.OUTPUT, FlushDirection.BOTH):
                    resource.reset_output_buffer()
            except Exception as exc:
                self._fault()
                raise TransportError(f"serial flush failed: {exc}") from exc

    def _read(self, resource: Any, request: ReadRequest) -> bytes:
        if request.mode is ReadMode.EXACT_LENGTH:
            assert request.length is not None
            chunks = bytearray()
            while len(chunks) < request.length:
                chunk = bytes(resource.read(request.length - len(chunks)))
                if not chunk:
                    raise TransportTimeoutError("serial exact-length read timed out")
                chunks.extend(chunk)
            return bytes(chunks)
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
            data = bytes(resource.read(request.length))
        else:
            waiting = min(int(resource.in_waiting), request.maximum_size)
            data = bytes(resource.read(waiting or 1))
            if data and len(data) < request.maximum_size:
                waiting = min(int(resource.in_waiting), request.maximum_size - len(data))
                if waiting:
                    data += bytes(resource.read(waiting))
        if not data:
            raise TransportTimeoutError("serial read timed out")
        if len(data) > request.maximum_size:
            raise TransportError("serial response exceeds maximum_size")
        return data

    def _require_open(self) -> Any:
        if self._state is not TransportState.OPEN or self._resource is None:
            raise NotConnectedError(f"transport is {self._state.name}, not OPEN")
        return self._resource

    def _fault(self) -> None:
        self._release()
        self._state = TransportState.FAULTED

    def _release(self) -> None:
        resource, self._resource = self._resource, None
        if resource is not None:
            resource.close()
