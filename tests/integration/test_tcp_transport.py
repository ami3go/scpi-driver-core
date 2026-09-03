from __future__ import annotations

import socket
import time
from collections.abc import Iterator
from contextlib import suppress

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    TransportError,
    TransportTimeoutError,
    UnsupportedOperationError,
)
from scpi_driver_core.transport import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    TcpTransport,
    Transport,
    TransportState,
)
from tests.integration.socket_endpoints import TcpEndpoint
from tests.transport_contract.contract import TransportContract


class _TestTcpTransport(TcpTransport):
    def __init__(self, endpoint: TcpEndpoint, **kwargs: object) -> None:
        self.endpoint = endpoint
        super().__init__(endpoint.address[0], endpoint.address[1], **kwargs)


@pytest.mark.integration
class TestTcpTransportContract(TransportContract):
    @pytest.fixture
    def transport(self) -> Iterator[Transport]:
        created = self.create_transport()
        assert isinstance(created, _TestTcpTransport)
        try:
            yield created
        finally:
            created.close()
            created.endpoint.close()

    def create_transport(self) -> Transport:
        return _TestTcpTransport(TcpEndpoint(), timeout_s=0.1)

    def prime(self, transport: Transport, data: bytes) -> None:
        assert isinstance(transport, _TestTcpTransport)
        transport.endpoint.send(data)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("", 5025), "host"),
        (("localhost", 0), "port"),
        (("localhost", 65_536), "port"),
    ],
)
def test_tcp_rejects_invalid_endpoint(args: tuple[str, int], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        TcpTransport(*args)


@pytest.mark.parametrize("name", ["connect_timeout_s", "timeout_s"])
def test_tcp_rejects_invalid_timeout(name: str) -> None:
    with pytest.raises(ConfigurationError, match=name):
        TcpTransport("localhost", 5025, **{name: 0.0})


def test_tcp_rejects_invalid_receive_chunk_size() -> None:
    with pytest.raises(ConfigurationError, match="receive_chunk_size"):
        TcpTransport("localhost", 5025, receive_chunk_size=0)


def test_tcp_descriptor() -> None:
    transport = TcpTransport("instrument.local", 5025, tcp_nodelay=False)
    assert transport.descriptor.kind == "tcp"
    assert transport.descriptor.address == "instrument.local:5025"
    assert transport.descriptor.metadata["tcp_nodelay"] == "False"


def test_tcp_preserves_overread_for_next_read() -> None:
    endpoint = TcpEndpoint()
    transport = _TestTcpTransport(endpoint)
    try:
        transport.open()
        endpoint.send(b"first\nsecond\n")
        request = ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")
        assert transport.read(request) == b"first"
        assert transport.read(request) == b"second"
    finally:
        transport.close()
        endpoint.close()


def test_tcp_detects_remote_disconnect() -> None:
    endpoint = TcpEndpoint()
    transport = _TestTcpTransport(endpoint)
    try:
        transport.open()
        endpoint.disconnect()
        with pytest.raises(TransportError, match="disconnected"):
            transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=1))
        assert transport.state is TransportState.FAULTED
    finally:
        transport.close()
        endpoint.close()


def test_tcp_backend_message_is_explicitly_unsupported() -> None:
    endpoint = TcpEndpoint()
    transport = _TestTcpTransport(endpoint)
    try:
        transport.open()
        with pytest.raises(UnsupportedOperationError):
            transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE))
        assert transport.state is TransportState.OPEN
    finally:
        transport.close()
        endpoint.close()


def test_tcp_input_flush_discards_pending_bytes() -> None:
    endpoint = TcpEndpoint()
    transport = _TestTcpTransport(endpoint)
    try:
        transport.open()
        endpoint.send(b"stale")
        time.sleep(0.02)
        transport.flush(FlushDirection.INPUT)
        with pytest.raises(TransportTimeoutError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE), timeout_s=0.05)
    finally:
        transport.close()
        endpoint.close()


def test_tcp_open_failure_is_translated_and_faults() -> None:
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    transport = TcpTransport("127.0.0.1", port, connect_timeout_s=0.1)
    with pytest.raises(TransportError) as caught:
        transport.open()
    assert caught.value.__cause__ is not None
    assert transport.state is TransportState.FAULTED
    with suppress(Exception):
        transport.close()
