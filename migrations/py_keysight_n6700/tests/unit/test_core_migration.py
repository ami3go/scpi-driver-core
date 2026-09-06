"""Migration proof: the VISA and TCP paths run through ``scpi-driver-core``.

The driver's pre-existing tests all drive the simulator, so they show that
nothing regressed but say nothing about the two transports the migration
actually replaced. These tests exercise those paths end to end: a real
``N6700`` object, over the real adapter, over the real core transport, against
a fake VISA backend and a loopback TCP server.

This is what section 42C of the core's task document asks for.
"""

from __future__ import annotations

import socket
import threading
from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest
import scpi_driver_core.transport.visa as core_visa
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import TcpTransport, VisaTransport

from py_keysight_n6700.driver import N6700
from py_keysight_n6700.exceptions import N6700CommandError, N6700ConnectionError
from py_keysight_n6700.transport import PyVisaTransport, RawSocketTransport

IDN = b"Keysight Technologies,N6700C,MY56000102,D.01.09\n"


# -- a fake VISA backend ---------------------------------------------------


class FakeVisaResource:
    def __init__(self, resource_name: str, **settings: Any) -> None:
        self.resource_name = resource_name
        self.settings = settings
        self.timeout = 0.0
        self.chunk_size = 0
        self.messages: deque[bytes] = deque()
        self.written = bytearray()
        self.closed = False

    def feed(self, data: bytes) -> None:
        self.messages.append(data)

    def write_raw(self, data: bytes) -> int:
        self.written.extend(data)
        command = data.decode("ascii").strip()
        if "?" in command:
            self.messages.append(_answer(command))
        return len(data)

    def read_raw(self, size: int | None = None) -> bytes:
        del size
        if not self.messages:
            raise _timeout()
        return self.messages.popleft()

    def read_bytes(self, count: int) -> bytes:
        taken = bytearray()
        while len(taken) < count:
            if not self.messages:
                raise _timeout()
            message = self.messages.popleft()
            needed = count - len(taken)
            if len(message) > needed:
                taken += message[:needed]
                self.messages.appendleft(message[needed:])
                break
            taken += message
        return bytes(taken)

    def clear(self) -> None:
        self.messages.clear()

    def close(self) -> None:
        self.closed = True


class FakeResourceManager:
    last: FakeVisaResource | None = None

    def __init__(self, visa_library: str = "") -> None:
        self.visa_library = visa_library
        self.closed = False

    def open_resource(self, resource_name: str, **settings: Any) -> FakeVisaResource:
        resource = FakeVisaResource(resource_name, **settings)
        FakeResourceManager.last = resource
        return resource

    def close(self) -> None:
        self.closed = True


def _timeout() -> Exception:
    error = Exception("VI_ERROR_TMO")
    error.error_code = -1073807339  # type: ignore[attr-defined]
    return error


def _answer(command: str) -> bytes:
    """Answer the handful of queries these tests provoke."""
    replies = {
        "*IDN?": IDN,
        "SYST:ERR?": b'0,"No error"\n',
        "*OPC?": b"1\n",
        "MEAS:VOLT? (@1)": b"12.0\n",
    }
    return replies.get(command, b'0,"No error"\n')


@pytest.fixture
def fake_visa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_visa, "_load_pyvisa", lambda: SimpleNamespace(ResourceManager=FakeResourceManager)
    )


# -- a loopback SCPI server ------------------------------------------------


class LoopbackInstrument:
    """A minimal newline-framed SCPI listener on localhost."""

    def __init__(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(1)
        self.port = self._server.getsockname()[1]
        self.received: list[str] = []
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self._server.accept()
        except OSError:  # pragma: no cover - only on teardown races
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
                    if "?" in command:
                        conn.sendall(_answer(command))

    def close(self) -> None:
        self._server.close()


@pytest.fixture
def loopback() -> Any:
    instrument = LoopbackInstrument()
    try:
        yield instrument
    finally:
        instrument.close()


# -- the VISA path ---------------------------------------------------------


def test_visa_transport_is_built_on_the_core(fake_visa: None) -> None:
    transport = PyVisaTransport("TCPIP0::192.0.2.10::inst0::INSTR")
    try:
        assert isinstance(transport.client, ScpiClient)
        assert isinstance(transport.client.transport, VisaTransport)
    finally:
        transport.close()


def test_visa_terminations_are_left_to_the_codec(fake_visa: None) -> None:
    """PyVISA must not trim payload bytes; the codec above it owns framing."""
    transport = PyVisaTransport("GPIB0::5::INSTR")
    try:
        settings = FakeResourceManager.last.settings  # type: ignore[union-attr]
        assert settings["read_termination"] is None
        assert settings["write_termination"] is None
    finally:
        transport.close()


def test_driver_connects_and_queries_over_visa(fake_visa: None) -> None:
    driver = N6700(PyVisaTransport("GPIB0::5::INSTR"), discover=False)
    try:
        identity = driver.idn()
        assert identity.manufacturer == "Keysight Technologies"
        assert identity.model == "N6700C"
        assert driver.query_scpi("MEAS:VOLT? (@1)") == "12.0"
        driver.write_scpi("*CLS")
        assert b"*CLS\n" in bytes(FakeResourceManager.last.written)  # type: ignore[union-attr]
    finally:
        driver.close()


def test_visa_timeout_becomes_the_drivers_own_error(fake_visa: None) -> None:
    from py_keysight_n6700.exceptions import N6700TimeoutError

    transport = PyVisaTransport("GPIB0::5::INSTR")
    try:
        with pytest.raises(N6700TimeoutError):
            transport.query("NO:REPLY")
    finally:
        transport.close()


def test_visa_open_failure_becomes_a_connection_error(
    fake_visa: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: FakeResourceManager, name: str, **settings: Any) -> Any:
        raise RuntimeError("no such resource")

    monkeypatch.setattr(FakeResourceManager, "open_resource", boom)
    with pytest.raises(N6700ConnectionError):
        PyVisaTransport("GPIB0::99::INSTR")


# -- the TCP path ----------------------------------------------------------


def test_tcp_transport_is_built_on_the_core(loopback: LoopbackInstrument) -> None:
    transport = RawSocketTransport("127.0.0.1", loopback.port)
    try:
        assert isinstance(transport.client.transport, TcpTransport)
    finally:
        transport.close()


def test_driver_connects_and_queries_over_tcp(loopback: LoopbackInstrument) -> None:
    driver = N6700(RawSocketTransport("127.0.0.1", loopback.port), discover=False)
    try:
        assert driver.idn().model == "N6700C"
        assert driver.query_scpi("MEAS:VOLT? (@1)") == "12.0"
        driver.write_scpi("*CLS")
    finally:
        driver.close()
    assert "*IDN?" in loopback.received
    assert "*CLS" in loopback.received


def test_tcp_connection_refused_becomes_a_connection_error() -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(N6700ConnectionError):
        RawSocketTransport("127.0.0.1", port, timeout_s=1.0)


def test_tcp_reports_clear_as_unsupported(loopback: LoopbackInstrument) -> None:
    """Preserved behavior: device clear is not faked over a raw socket."""
    from py_keysight_n6700.exceptions import UnsupportedFeatureError

    transport = RawSocketTransport("127.0.0.1", loopback.port)
    try:
        assert transport.supports_clear is False
        with pytest.raises(UnsupportedFeatureError):
            transport.clear()
    finally:
        transport.close()


# -- behavior preserved across the migration -------------------------------


def test_manufacturer_policy_still_lives_in_the_driver(fake_visa: None) -> None:
    """The core parses identity; deciding what is acceptable stays here."""
    from py_keysight_n6700.scpi import parse_idn

    with pytest.raises(N6700CommandError, match="unsupported manufacturer"):
        parse_idn("ACME Instruments,N6700C,SN1,1.0")


def test_channel_list_syntax_stayed_device_specific() -> None:
    """(@1:4) is N6700 grammar and has no business in a generic core."""
    from py_keysight_n6700.scpi import format_channel_list, parse_channel_list

    assert format_channel_list(range(1, 5)) == "(@1:4)"
    assert parse_channel_list("(@1:3,4)") == [1, 2, 3, 4]
