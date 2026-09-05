"""Migration proof: the TCP, UDP and RS232 paths run through ``scpi-driver-core``.

Section 42D of the core's task document names this driver for TCP, UDP, RS232
and multiple aliases. It is the only one of the six migrated so far that is not
VISA, so it is what shows the core's socket and serial backends carrying a real
driver rather than only its own conformance suite.

The pre-existing tests do not touch the transports at all, so everything the
migration replaced is covered here: a loopback TCP server, a real UDP socket, and
a faked pyserial backend.
"""

from __future__ import annotations

import socket
import threading
import time
from types import SimpleNamespace
from typing import Any

import pytest

import scpi_driver_core.transport.serial as core_serial
from ngi_n83624.exceptions import CommunicationError, TimeoutError, ValidationError
from ngi_n83624.transports import (
    SerialTransport,
    TcpTransport,
    UdpTransport,
    udp_channel,
)
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import SerialTransport as CoreSerialTransport
from scpi_driver_core.transport import TcpTransport as CoreTcpTransport
from scpi_driver_core.transport import UdpTransport as CoreUdpTransport


def wait_for(received: list[str], command: str, *, timeout_s: float = 2.0) -> None:
    """Wait for the server thread to record ``command``.

    A UDP write is fire-and-forget and a TCP write returns before the peer has
    processed anything, so asserting on the server's log immediately is a race.
    This waits instead of sleeping a fixed amount, so it is neither flaky nor
    slow.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if command in received:
            return
        time.sleep(0.01)
    raise AssertionError(f"{command!r} never reached the instrument; got {received}")


def _answer(command: str) -> bytes:
    replies = {
        "*IDN?": b"NGI,N83624,SN12345,1.00\n",
        "MEAS:VOLT?": b"12.345\n",
        "SYST:ERR?": b'0,"No error"\n',
    }
    return replies.get(command, b"OK\n")


# -- a loopback TCP instrument ---------------------------------------------


class LoopbackTcp:
    def __init__(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self.port = self._server.getsockname()[1]
        self.received: list[str] = []
        self.silent = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self._server.accept()
        except OSError:  # pragma: no cover - teardown race
            return
        with conn:
            buffer = b""
            while True:
                try:
                    chunk = conn.recv(4096)
                except OSError:  # pragma: no cover - teardown
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    command = line.decode("ascii").strip()
                    self.received.append(command)
                    if self.silent:
                        continue
                    if command.endswith("PARTIAL"):
                        conn.sendall(b"no terminator here")  # deliberately unterminated
                    elif "?" in command:
                        conn.sendall(_answer(command))

    def close(self) -> None:
        self._server.close()


@pytest.fixture
def tcp_instrument() -> Any:
    instrument = LoopbackTcp()
    try:
        yield instrument
    finally:
        instrument.close()


# -- a loopback UDP instrument ---------------------------------------------


class LoopbackUdp:
    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("127.0.0.1", 0))
        self.port = self._sock.getsockname()[1]
        self.received: list[str] = []
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(4096)
            except OSError:  # pragma: no cover - teardown
                return
            command = data.decode("ascii").strip()
            self.received.append(command)
            if "?" in command:
                self._sock.sendto(_answer(command), addr)

    def close(self) -> None:
        self._running = False
        self._sock.close()


@pytest.fixture
def udp_instrument() -> Any:
    instrument = LoopbackUdp()
    try:
        yield instrument
    finally:
        instrument.close()


# -- a fake pyserial backend -----------------------------------------------


class FakeSerial:
    last: FakeSerial | None = None

    def __init__(self, **settings: Any) -> None:
        self.settings = settings
        self.timeout = settings.get("timeout")
        self.write_timeout = settings.get("write_timeout")
        self.inbound = bytearray()
        self.written = bytearray()
        self.is_open = True
        FakeSerial.last = self

    def write(self, data: bytes) -> int:
        self.written.extend(data)
        command = data.decode("ascii").strip()
        if "?" in command:
            self.inbound.extend(_answer(command))
        return len(data)

    def read(self, size: int) -> bytes:
        count = min(size, len(self.inbound))
        data = bytes(self.inbound[:count])
        del self.inbound[:count]
        return data

    def read_until(self, expected: bytes, size: int) -> bytes:
        end = self.inbound.find(expected)
        count = min(size, len(self.inbound) if end < 0 else end + len(expected))
        return self.read(count)

    @property
    def in_waiting(self) -> int:
        return len(self.inbound)

    def reset_input_buffer(self) -> None:
        self.inbound.clear()

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.is_open = False


@pytest.fixture
def fake_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSerial.last = None
    monkeypatch.setattr(core_serial, "_load_serial", lambda: SimpleNamespace(Serial=FakeSerial))


# -- TCP -------------------------------------------------------------------


def test_tcp_is_built_on_the_core(tcp_instrument: LoopbackTcp) -> None:
    transport = TcpTransport(host="127.0.0.1", port=tcp_instrument.port)
    transport.open()
    try:
        assert isinstance(transport._client, ScpiClient)
        assert isinstance(transport._client.transport, CoreTcpTransport)
    finally:
        transport.close()


def test_tcp_query_round_trip(tcp_instrument: LoopbackTcp) -> None:
    transport = TcpTransport(host="127.0.0.1", port=tcp_instrument.port)
    transport.open()
    try:
        assert transport.query("*IDN?") == "NGI,N83624,SN12345,1.00"
        assert transport.query("MEAS:VOLT?") == "12.345"
        transport.write("OUTP ON")
        wait_for(tcp_instrument.received, "OUTP ON")
    finally:
        transport.close()


def test_tcp_open_close_is_idempotent(tcp_instrument: LoopbackTcp) -> None:
    transport = TcpTransport(host="127.0.0.1", port=tcp_instrument.port)
    transport.open()
    transport.open()
    assert transport.is_open() is True
    transport.close()
    transport.close()
    assert transport.is_open() is False


def test_tcp_io_before_open_is_refused() -> None:
    transport = TcpTransport(host="127.0.0.1", port=7000)
    with pytest.raises(CommunicationError):
        transport.query("*IDN?")


def test_tcp_connect_failure_is_a_communication_error() -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    transport = TcpTransport(host="127.0.0.1", port=port, timeout=1.0)
    with pytest.raises(CommunicationError):
        transport.open()


def test_tcp_query_timeout(tcp_instrument: LoopbackTcp) -> None:
    tcp_instrument.silent = True
    transport = TcpTransport(host="127.0.0.1", port=tcp_instrument.port, timeout=0.5)
    transport.open()
    try:
        with pytest.raises(TimeoutError):
            transport.query("*IDN?")
    finally:
        transport.close()


def test_tcp_returns_a_partial_reply_rather_than_losing_it(
    tcp_instrument: LoopbackTcp,
) -> None:
    """Preserved leniency: data that arrived without a terminator is still returned."""
    transport = TcpTransport(host="127.0.0.1", port=tcp_instrument.port, timeout=0.5)
    transport.open()
    try:
        assert transport.query("READ:PARTIAL") == "no terminator here"
    finally:
        transport.close()


def test_tcp_port_validation_stayed_in_the_driver() -> None:
    with pytest.raises(ValidationError):
        TcpTransport(host="127.0.0.1", port=0)
    with pytest.raises(ValidationError):
        TcpTransport(host="127.0.0.1", port=70000)


# -- UDP -------------------------------------------------------------------


def test_udp_is_built_on_the_core(udp_instrument: LoopbackUdp) -> None:
    transport = UdpTransport(host="127.0.0.1", port=7000)
    object.__setattr__(transport, "port", udp_instrument.port)
    transport.open()
    try:
        assert isinstance(transport._client.transport, CoreUdpTransport)
    finally:
        transport.close()


def test_udp_query_round_trip(udp_instrument: LoopbackUdp) -> None:
    transport = UdpTransport(host="127.0.0.1", port=7000)
    object.__setattr__(transport, "port", udp_instrument.port)
    transport.open()
    try:
        assert transport.query("*IDN?") == "NGI,N83624,SN12345,1.00"
        transport.write("OUTP ON")
        wait_for(udp_instrument.received, "OUTP ON")
    finally:
        transport.close()


def test_udp_query_timeout() -> None:
    """Nothing is listening, so the datagram is never answered."""
    transport = UdpTransport(host="127.0.0.1", port=7000, timeout=0.4)
    object.__setattr__(transport, "port", 1)  # reserved, nothing replies
    transport.open()
    try:
        with pytest.raises(TimeoutError):
            transport.query("*IDN?")
    finally:
        transport.close()


def test_udp_channel_port_mapping_stayed_in_the_driver() -> None:
    """7001..7024 map to channels 1..24. That is this instrument's scheme."""
    transport = udp_channel("192.168.0.123", 7)
    assert transport.port == 7007
    assert transport.single_channel == 7


def test_udp_port_range_is_enforced() -> None:
    with pytest.raises(ValidationError):
        UdpTransport(host="127.0.0.1", port=6999)
    with pytest.raises(ValidationError):
        UdpTransport(host="127.0.0.1", port=7025)


def test_udp_channel_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UdpTransport(host="127.0.0.1", port=7003, single_channel=5)


# -- RS232 -----------------------------------------------------------------


def test_serial_is_built_on_the_core(fake_serial: None) -> None:
    transport = SerialTransport(port="/dev/ttyUSB0")
    transport.open()
    try:
        assert isinstance(transport._client.transport, CoreSerialTransport)
    finally:
        transport.close()


def test_serial_query_round_trip(fake_serial: None) -> None:
    transport = SerialTransport(port="/dev/ttyUSB0")
    transport.open()
    try:
        assert transport.query("*IDN?") == "NGI,N83624,SN12345,1.00"
        transport.write("OUTP ON")
        assert bytes(FakeSerial.last.written).endswith(b"OUTP ON\n")  # type: ignore[union-attr]
    finally:
        transport.close()


def test_serial_settings_are_forwarded(fake_serial: None) -> None:
    transport = SerialTransport(port="/dev/ttyUSB0", baudrate=9600, timeout=2.0)
    transport.open()
    try:
        settings = FakeSerial.last.settings  # type: ignore[union-attr]
        assert settings["port"] == "/dev/ttyUSB0"
        assert settings["baudrate"] == 9600
        assert settings["timeout"] == 2.0
    finally:
        transport.close()


def test_serial_io_before_open_is_refused(fake_serial: None) -> None:
    transport = SerialTransport(port="/dev/ttyUSB0")
    with pytest.raises(CommunicationError):
        transport.query("*IDN?")


def test_serial_baudrate_validation_stayed_in_the_driver() -> None:
    with pytest.raises(ValidationError):
        SerialTransport(port="/dev/ttyUSB0", baudrate=12345)


def test_serial_close_marks_it_closed(fake_serial: None) -> None:
    transport = SerialTransport(port="/dev/ttyUSB0")
    transport.open()
    assert transport.is_open() is True
    transport.close()
    assert transport.is_open() is False


# -- shared framing --------------------------------------------------------


def test_empty_commands_are_still_rejected() -> None:
    from ngi_n83624.transports import _encode_command

    for bad in ("", "   ", "\n"):
        with pytest.raises(ValidationError):
            _encode_command(bad)


def test_the_terminator_is_appended_once() -> None:
    from ngi_n83624.transports import _encode_command

    assert _encode_command("*IDN?") == b"*IDN?\n"
    assert _encode_command("*IDN?\n") == b"*IDN?\n"
