"""Datagram-preserving UDP transport."""

from __future__ import annotations

import socket
import time

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
from scpi_driver_core.transport.state import TransportStateMachine

__all__ = ["UdpTransport"]

_STALE_DRAIN_BUDGET = 256


class UdpTransport(TransportStateMachine):
    """A bounded UDP transport preserving one datagram per read.

    A read timeout faults and closes the socket. With an ephemeral local port,
    any late reply therefore targets a socket that no longer exists. With a
    caller-supplied fixed ``local_bind`` port a network race is inherently still
    possible; protocols that echo a transaction tag should validate it above
    this generic transport.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        timeout_s: float = 5.0,
        maximum_datagram_size: int = 65_507,
        local_bind: tuple[str, int] | None = None,
        validate_source: bool = True,
    ) -> None:
        if not host:
            raise ConfigurationError("host must not be empty")
        if not 1 <= port <= 65_535:
            raise ConfigurationError(f"port must be between 1 and 65535, got {port!r}")
        validate_timeout(timeout_s, "timeout_s")
        if not 1 <= maximum_datagram_size <= 65_507:
            raise ConfigurationError("maximum_datagram_size must be between 1 and 65507")
        if local_bind is not None and not 0 <= local_bind[1] <= 65_535:
            raise ConfigurationError("local bind port must be between 0 and 65535")

        self._host = host
        self._port = port
        self._timeout_s = timeout_s
        self._maximum_datagram_size = maximum_datagram_size
        self._local_bind = local_bind
        self._validate_source = validate_source
        self._remote: tuple[str, int] | None = None
        self._socket: socket.socket | None = None
        self._stale_discarded = 0
        super().__init__(
            TransportDescriptor(
                kind="udp",
                address=f"{host}:{port}",
                metadata={"validate_source": str(validate_source)},
            )
        )

    @property
    def stale_datagrams_discarded(self) -> int:
        return self._stale_discarded

    def open(self) -> TransportDescriptor:
        with self._lock:
            if self.state is TransportState.OPEN:
                return self._descriptor
            self._release_resource()
            self._set_state(TransportState.OPENING)
            resource: socket.socket | None = None
            try:
                addresses = socket.getaddrinfo(
                    self._host, self._port, type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP
                )
                if not addresses:
                    raise OSError("host resolution returned no addresses")
                family, socket_type, protocol, _, remote = addresses[0]
                resource = socket.socket(family, socket_type, protocol)
                if self._local_bind is not None:
                    resource.bind(self._local_bind)
                resource.settimeout(self._timeout_s)
            except (OSError, UnicodeError, ValueError) as exc:
                if resource is not None:
                    resource.close()
                self._set_state(TransportState.FAULTED)
                if isinstance(exc, OSError):
                    raise translate_socket_error(exc, "open") from exc
                raise ConfigurationError(f"UDP open failed for {self._host!r}: {exc}") from exc
            self._socket = resource
            self._remote = (str(remote[0]), int(remote[1]))
            self._set_state(TransportState.OPEN)
            return self._descriptor

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        del operation_id
        if len(data) > self._maximum_datagram_size:
            raise ConfigurationError(
                f"datagram of {len(data)} bytes exceeds maximum_datagram_size "
                f"{self._maximum_datagram_size}"
            )
        timeout = effective_timeout(timeout_s, self._timeout_s)
        with self._lock:
            resource, remote = self._require_open()
            with self._faulting_io():
                try:
                    resource.settimeout(timeout)
                    count = resource.sendto(data, remote)
                    if count != len(data):
                        raise TransportError(f"UDP sent {count} of {len(data)} bytes")
                except OSError as exc:
                    raise translate_socket_error(exc, "write") from exc
            return WriteResult(bytes_written=count)

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
            resource, remote = self._require_open()
            deadline = time.monotonic() + timeout
            with self._faulting_io():
                try:
                    while True:
                        resource.settimeout(remaining(deadline))
                        data, source = resource.recvfrom(self._maximum_datagram_size + 1)
                        normalized_source = (str(source[0]), int(source[1]))
                        if self._validate_source and normalized_source != remote:
                            continue
                        break
                except TimeoutError as exc:
                    raise TransportTimeoutError("UDP read timed out") from exc
                except OSError as exc:
                    raise translate_socket_error(exc, "read") from exc

                if len(data) > self._maximum_datagram_size:
                    raise TransportError("received datagram exceeds maximum_datagram_size")
                if len(data) > request.maximum_size:
                    raise TransportError("received datagram exceeds request.maximum_size")
                return self._apply_request(data, request)

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
            stale = self._discard_stale_datagrams()
            self._stale_discarded += stale
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        with self._lock:
            self._require_open()
            if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                self._stale_discarded += self._discard_stale_datagrams()

    def _discard_stale_datagrams(self, budget: int = _STALE_DRAIN_BUDGET) -> int:
        resource, _ = self._require_open()
        previous_timeout = resource.gettimeout()
        discarded = 0
        try:
            resource.setblocking(False)
            while discarded < budget:
                try:
                    resource.recvfrom(self._maximum_datagram_size + 1)
                except (BlockingIOError, InterruptedError):
                    break
                discarded += 1
        except OSError as exc:
            raise translate_socket_error(exc, "input drain") from exc
        finally:
            if self._socket is resource:
                resource.settimeout(previous_timeout)
        return discarded

    def _apply_request(self, data: bytes, request: ReadRequest) -> bytes:
        if request.mode in (ReadMode.AVAILABLE, ReadMode.BACKEND_DEFINED_MESSAGE):
            return data
        if request.mode is ReadMode.EXACT_LENGTH:
            assert request.length is not None
            if len(data) != request.length:
                raise TransportError(
                    f"datagram length {len(data)} does not equal requested length {request.length}"
                )
            return data
        if request.mode is ReadMode.UP_TO_LENGTH:
            assert request.length is not None
            if len(data) > request.length:
                raise TransportError(
                    f"datagram length {len(data)} exceeds requested length {request.length}"
                )
            return data
        if request.mode is ReadMode.UNTIL_TERMINATOR:
            assert request.terminator is not None
            if not data.endswith(request.terminator):
                raise TransportError("datagram does not end with the requested terminator")
            return data if request.include_terminator else data[: -len(request.terminator)]
        raise UnsupportedOperationError(f"unsupported UDP read mode {request.mode!r}")

    def _require_open(self) -> tuple[socket.socket, tuple[str, int]]:
        self._require_state_open()
        if self._socket is None or self._remote is None:
            raise NotConnectedError("transport is OPEN but holds no socket")
        return self._socket, self._remote

    def _release_resource(self) -> None:
        resource, self._socket = self._socket, None
        self._remote = None
        if resource is not None:
            resource.close()
