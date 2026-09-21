from __future__ import annotations

import socket
import time

import pytest

from scpi_driver_core.exceptions import ConfigurationError, TransportError, TransportTimeoutError
from scpi_driver_core.transport import (
    ReadMode,
    ReadRequest,
    Transport,
    TransportState,
    UdpTransport,
)
from tests.integration.socket_endpoints import UdpEndpoint
from tests.transport_contract.contract import TransportContract


class _TestUdpTransport(UdpTransport):
    def __init__(self, endpoint: UdpEndpoint, **kwargs: object) -> None:
        self.endpoint = endpoint
        super().__init__(
            endpoint.address[0], endpoint.address[1], local_bind=("127.0.0.1", 0), **kwargs
        )

    @property
    def local_address(self) -> tuple[str, int]:
        assert self._socket is not None
        address = self._socket.getsockname()
        return str(address[0]), int(address[1])

    def close(self) -> None:
        super().close()
        self.endpoint.close()


@pytest.mark.integration
class TestUdpTransportContract(TransportContract):
    supports_exact_stream_reads = False

    def create_transport(self) -> Transport:
        return _TestUdpTransport(UdpEndpoint(), timeout_s=0.1)

    def prime(self, transport: Transport, data: bytes) -> None:
        assert isinstance(transport, _TestUdpTransport)
        transport.endpoint.send(data, transport.local_address)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("", 5025), "host"),
        (("localhost", 0), "port"),
        (("localhost", 65_536), "port"),
    ],
)
def test_udp_rejects_invalid_endpoint(args: tuple[str, int], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        UdpTransport(*args)


@pytest.mark.parametrize("size", [0, 65_508])
def test_udp_rejects_invalid_datagram_size(size: int) -> None:
    with pytest.raises(ConfigurationError, match="maximum_datagram_size"):
        UdpTransport("localhost", 5025, maximum_datagram_size=size)


def test_udp_rejects_invalid_local_port() -> None:
    with pytest.raises(ConfigurationError, match="local bind port"):
        UdpTransport("localhost", 5025, local_bind=("127.0.0.1", 65_536))


def test_udp_rejects_oversize_write_before_sending() -> None:
    endpoint = UdpEndpoint()
    transport = _TestUdpTransport(endpoint, maximum_datagram_size=4)
    try:
        transport.open()
        with pytest.raises(ConfigurationError, match="exceeds"):
            transport.write(b"12345")
        assert endpoint.received == []
    finally:
        transport.close()


def test_udp_one_read_consumes_one_datagram() -> None:
    endpoint = UdpEndpoint()
    transport = _TestUdpTransport(endpoint)
    try:
        transport.open()
        endpoint.send(b"one", transport.local_address)
        endpoint.send(b"two", transport.local_address)
        request = ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)
        assert transport.read(request) == b"one"
        assert transport.read(request) == b"two"
    finally:
        transport.close()


def test_udp_does_not_truncate_up_to_length() -> None:
    endpoint = UdpEndpoint()
    transport = _TestUdpTransport(endpoint)
    try:
        transport.open()
        endpoint.send(b"12345", transport.local_address)
        with pytest.raises(TransportError, match="exceeds requested length"):
            transport.read(ReadRequest(mode=ReadMode.UP_TO_LENGTH, length=4))
    finally:
        transport.close()


def test_udp_source_validation_ignores_other_sender() -> None:
    endpoint = UdpEndpoint()
    transport = _TestUdpTransport(endpoint, timeout_s=0.1)
    other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        transport.open()
        other.sendto(b"spoof", transport.local_address)
        with pytest.raises(TransportTimeoutError):
            transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE))
        assert transport.state is TransportState.FAULTED
    finally:
        other.close()
        transport.close()


def test_udp_source_validation_can_be_disabled() -> None:
    endpoint = UdpEndpoint()
    transport = _TestUdpTransport(endpoint, validate_source=False)
    other = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        transport.open()
        other.sendto(b"accepted", transport.local_address)
        assert transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)) == b"accepted"
    finally:
        other.close()
        transport.close()


def test_udp_transact_sends_only_once() -> None:
    endpoint = UdpEndpoint()
    transport = _TestUdpTransport(endpoint)
    try:
        transport.open()
        endpoint.send(b"reply", transport.local_address)
        assert (
            transport.transact(b"command", ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE))
            == b"reply"
        )
        deadline = time.monotonic() + 1
        while not endpoint.received and time.monotonic() < deadline:
            time.sleep(0.005)
        assert [data for data, _ in endpoint.received] == [b"command"]
    finally:
        transport.close()
