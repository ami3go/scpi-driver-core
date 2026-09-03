"""Raw, byte-preserving TCP transport."""

from __future__ import annotations

import select
import socket
import threading
import time
from contextlib import suppress

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
from scpi_driver_core.transport.socket_utils import (
    effective_timeout,
    remaining,
    translate_socket_error,
    validate_timeout,
)

__all__ = ["TcpTransport"]


class TcpTransport:
    """A bounded raw TCP connection which never adds protocol framing."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout_s: float = 5.0,
        timeout_s: float = 5.0,
        tcp_nodelay: bool = True,
        receive_chunk_size: int = 4096,
    ) -> None:
        if not host:
            raise ConfigurationError("host must not be empty")
        if not 1 <= port <= 65_535:
            raise ConfigurationError(f"port must be between 1 and 65535, got {port!r}")
        validate_timeout(connect_timeout_s, "connect_timeout_s")
        validate_timeout(timeout_s, "timeout_s")
        if receive_chunk_size <= 0:
            raise ConfigurationError("receive_chunk_size must be positive")

        self._host = host
        self._port = port
        self._connect_timeout_s = connect_timeout_s
        self._timeout_s = timeout_s
        self._tcp_nodelay = tcp_nodelay
        self._receive_chunk_size = receive_chunk_size
        self._descriptor = TransportDescriptor(
            kind="tcp", address=f"{host}:{port}", metadata={"tcp_nodelay": str(tcp_nodelay)}
        )
        self._state = TransportState.CREATED
        self._socket: socket.socket | None = None
        self._buffer = bytearray()
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
            self._release()
            self._state = TransportState.OPENING
            resource: socket.socket | None = None
            try:
                resource = socket.create_connection(
                    (self._host, self._port), timeout=self._connect_timeout_s
                )
                resource.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, int(self._tcp_nodelay))
                resource.settimeout(self._timeout_s)
            except OSError as exc:
                if resource is not None:
                    resource.close()
                self._state = TransportState.FAULTED
                raise translate_socket_error(exc, "connect") from exc
            self._socket = resource
            self._buffer.clear()
            self._state = TransportState.OPEN
            return self._descriptor

    def close(self) -> None:
        with self._lock:
            if self._state in (TransportState.CREATED, TransportState.CLOSED):
                return
            self._state = TransportState.CLOSING
            self._release()
            self._buffer.clear()
            self._state = TransportState.CLOSED

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
            deadline = time.monotonic() + timeout
            sent = 0
            try:
                while sent < len(data):
                    resource.settimeout(remaining(deadline))
                    count = resource.send(data[sent:])
                    if count == 0:
                        raise TransportError("TCP peer disconnected during write")
                    sent += count
            except (OSError, TransportError, TransportTimeoutError) as exc:
                self._fault()
                if isinstance(exc, OSError):
                    raise translate_socket_error(exc, "write") from exc
                raise
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
            self._require_open()
            if request.mode is ReadMode.BACKEND_DEFINED_MESSAGE:
                raise UnsupportedOperationError("TCP is a byte stream and has no message boundary")
            deadline = time.monotonic() + timeout
            try:
                return self._read(request, deadline)
            except (OSError, TransportError, TransportTimeoutError) as exc:
                self._fault()
                if isinstance(exc, OSError):
                    raise translate_socket_error(exc, "read") from exc
                raise

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
            if direction not in (FlushDirection.INPUT, FlushDirection.BOTH):
                return
            self._buffer.clear()
            try:
                while select.select([resource], [], [], 0)[0]:
                    if not resource.recv(self._receive_chunk_size):
                        self._fault()
                        raise TransportError("TCP peer disconnected while flushing input")
            except OSError as exc:
                self._fault()
                raise translate_socket_error(exc, "flush") from exc

    def _read(self, request: ReadRequest, deadline: float) -> bytes:
        if request.mode is ReadMode.EXACT_LENGTH:
            assert request.length is not None
            self._fill_to(request.length, request.maximum_size, deadline)
            return self._take(request.length)
        if request.mode is ReadMode.UNTIL_TERMINATOR:
            assert request.terminator is not None
            while True:
                end = self._buffer.find(request.terminator)
                if end >= 0:
                    count = end + len(request.terminator)
                    if count > request.maximum_size:
                        raise TransportError("response exceeds maximum_size")
                    data = self._take(count)
                    return data if request.include_terminator else data[: -len(request.terminator)]
                if len(self._buffer) >= request.maximum_size:
                    raise TransportError("terminator not found before maximum_size")
                self._receive(request.maximum_size - len(self._buffer), deadline)
        if request.mode is ReadMode.UP_TO_LENGTH:
            assert request.length is not None
            if not self._buffer:
                self._receive(min(request.length, request.maximum_size), deadline)
            return self._take(min(request.length, len(self._buffer)))
        if not self._buffer:
            self._receive(request.maximum_size, deadline)
        self._receive_available(request.maximum_size)
        return self._take(min(len(self._buffer), request.maximum_size))

    def _fill_to(self, count: int, maximum_size: int, deadline: float) -> None:
        if count > maximum_size:
            raise TransportError("requested length exceeds maximum_size")
        while len(self._buffer) < count:
            self._receive(min(self._receive_chunk_size, maximum_size - len(self._buffer)), deadline)

    def _receive(self, count: int, deadline: float) -> None:
        resource = self._require_open()
        resource.settimeout(remaining(deadline))
        chunk = resource.recv(max(1, count))
        if not chunk:
            raise TransportError("TCP peer disconnected during read")
        self._buffer.extend(chunk)

    def _receive_available(self, maximum_size: int) -> None:
        resource = self._require_open()
        while len(self._buffer) < maximum_size and select.select([resource], [], [], 0)[0]:
            chunk = resource.recv(min(self._receive_chunk_size, maximum_size - len(self._buffer)))
            if not chunk:
                raise TransportError("TCP peer disconnected during read")
            self._buffer.extend(chunk)

    def _take(self, count: int) -> bytes:
        data = bytes(self._buffer[:count])
        del self._buffer[:count]
        return data

    def _require_open(self) -> socket.socket:
        if self._state is not TransportState.OPEN or self._socket is None:
            raise NotConnectedError(f"transport is {self._state.name}, not OPEN")
        return self._socket

    def _fault(self) -> None:
        self._release()
        self._state = TransportState.FAULTED

    def _release(self) -> None:
        resource, self._socket = self._socket, None
        if resource is not None:
            with suppress(OSError):
                resource.shutdown(socket.SHUT_RDWR)
            resource.close()
