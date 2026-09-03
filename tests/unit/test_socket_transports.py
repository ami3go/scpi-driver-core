from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from scpi_driver_core.exceptions import TransportError
from scpi_driver_core.transport import TcpTransport, TransportState


class FakeSocket:
    def __init__(self, send_sizes: Iterator[int] | None = None) -> None:
        self.send_sizes = iter(()) if send_sizes is None else send_sizes
        self.sent = bytearray()
        self.closed = False
        self.timeout: float | None = None

    def setsockopt(self, level: int, option: int, value: int) -> None:
        del level, option, value

    def settimeout(self, value: float | None) -> None:
        self.timeout = value

    def send(self, data: bytes) -> int:
        size = next(self.send_sizes, len(data))
        self.sent.extend(data[:size])
        return size

    def shutdown(self, how: int) -> None:
        del how

    def close(self) -> None:
        self.closed = True


def install_fake_socket(monkeypatch: pytest.MonkeyPatch, fake: FakeSocket) -> None:
    monkeypatch.setattr(socket, "create_connection", lambda *args, **kwargs: fake)


def test_tcp_loops_until_partial_writes_are_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(iter([2, 1, 3]))
    install_fake_socket(monkeypatch, fake)
    transport = TcpTransport("instrument", 5025)
    transport.open()
    assert transport.write(b"abcdef").bytes_written == 6
    assert fake.sent == b"abcdef"


def test_tcp_zero_byte_send_faults_as_disconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeSocket(iter([0]))
    install_fake_socket(monkeypatch, fake)
    transport = TcpTransport("instrument", 5025)
    transport.open()
    with pytest.raises(TransportError, match="disconnected"):
        transport.write(b"data")
    assert transport.state is TransportState.FAULTED
    assert fake.closed


def test_tcp_closes_socket_when_setup_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class SetupFailureSocket(FakeSocket):
        def setsockopt(self, level: int, option: int, value: int) -> None:
            del level, option, value
            raise OSError("option failed")

    fake = SetupFailureSocket()
    install_fake_socket(monkeypatch, fake)
    transport = TcpTransport("instrument", 5025)
    with pytest.raises(TransportError, match="connect") as caught:
        transport.open()
    assert caught.value.__cause__ is not None
    assert fake.closed
    assert transport.state is TransportState.FAULTED
