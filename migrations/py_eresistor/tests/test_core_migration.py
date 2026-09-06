"""Migration proof: the SCPI-over-TCP path runs through ``scpi-driver-core``.

Section 42 lists the E-Resistor SCPI path as secondary validation, and section 3
is explicit that only that path is in scope: the HTTP fallback stays
device-specific and is untouched here.

The driver's pre-existing tests cover the Robot adapter and evidence layers and
never open a socket, so everything the migration replaced is covered here
against a loopback TCP server.
"""

from __future__ import annotations

import socket
import threading
from typing import Any

import pytest

from py_eresistor_driver.scpi import ScpiTransport
from py_eresistor_driver.exceptions import ConnectionError, ScpiError
from py_eresistor_driver.models import ConnectionState
from scpi_driver_core.transport import TcpTransport as CoreTcpTransport


class LoopbackInstrument:
    """A minimal newline-framed SCPI listener, with the knobs these tests need."""

    def __init__(self, *, greeting: bytes | None = None) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(("127.0.0.1", 0))
        self._server.listen(5)
        self.port = self._server.getsockname()[1]
        self.greeting = greeting
        self.received: list[str] = []
        self.connections = 0
        self.silent = False
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while self._running:
            try:
                conn, _ = self._server.accept()
            except OSError:  # pragma: no cover - teardown
                return
            self.connections += 1
            threading.Thread(target=self._session, args=(conn,), daemon=True).start()

    def _session(self, conn: socket.socket) -> None:
        with conn:
            if self.greeting:
                conn.sendall(self.greeting)
            buffer = b""
            while self._running:
                try:
                    chunk = conn.recv(4096)
                except OSError:  # pragma: no cover - teardown
                    return
                if not chunk:
                    return
                buffer += chunk
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    command = line.decode("utf-8").strip()
                    self.received.append(command)
                    if self.silent:
                        continue
                    conn.sendall(self._answer(command))

    @staticmethod
    def _answer(command: str) -> bytes:
        if command == "*IDN?":
            return b"ERESISTOR,ER-1,SN001,1.2.3\n"
        if command == "MEAS:RES?":
            return b"1234.5\n"
        if command == "BAD:COMMAND":
            # This instrument prefixes errors with ERR, which is its own framing
            # and stayed in the driver rather than moving to the core.
            return b'ERR,-113,"Undefined header"\n'
        if command == "LIST:ALL?":
            return b"#BEGIN\nline one\nline two\n#END ALL\n"
        return b"OK\n"

    def close(self) -> None:
        self._running = False
        self._server.close()


@pytest.fixture
def instrument() -> Any:
    server = LoopbackInstrument()
    try:
        yield server
    finally:
        server.close()


def connected(server: LoopbackInstrument, **kwargs: Any) -> ScpiTransport:
    transport = ScpiTransport("127.0.0.1", server.port, timeout=1.0, **kwargs)
    transport.connect()
    return transport


# -- the transport is the core's -------------------------------------------


def test_transport_is_built_on_the_core(instrument: LoopbackInstrument) -> None:
    transport = connected(instrument)
    try:
        assert isinstance(transport._transport, CoreTcpTransport)
    finally:
        transport.close()


def test_connect_reports_connected(instrument: LoopbackInstrument) -> None:
    transport = connected(instrument)
    try:
        assert transport.state is ConnectionState.CONNECTED
        assert transport.last_success_monotonic is not None
    finally:
        transport.close()


def test_close_is_idempotent(instrument: LoopbackInstrument) -> None:
    transport = connected(instrument)
    transport.close()
    transport.close()
    assert transport.state is ConnectionState.DISCONNECTED


def test_connect_failure_reports_lost() -> None:
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    transport = ScpiTransport("127.0.0.1", port, timeout=1.0, retries=0)
    with pytest.raises(ConnectionError):
        transport.connect()
    assert transport.state is ConnectionState.LOST


# -- request / response ----------------------------------------------------


def test_request_round_trip(instrument: LoopbackInstrument) -> None:
    transport = connected(instrument)
    try:
        assert transport.request("*IDN?") == "ERESISTOR,ER-1,SN001,1.2.3"
        assert transport.request("MEAS:RES?") == "1234.5"
    finally:
        transport.close()
    assert "*IDN?" in instrument.received


def test_multiline_request(instrument: LoopbackInstrument) -> None:
    """Multi-line framing is this instrument's, and stayed in the driver."""
    transport = connected(instrument)
    try:
        response = transport.request("LIST:ALL?", multiline_until="#END ALL")
        assert response.splitlines()[-1] == "#END ALL"
        assert "line one" in response
    finally:
        transport.close()


def test_a_device_error_reply_raises(instrument: LoopbackInstrument) -> None:
    transport = connected(instrument)
    try:
        with pytest.raises(ScpiError):
            transport.request("BAD:COMMAND")
    finally:
        transport.close()


def test_request_timeout_is_reported(instrument: LoopbackInstrument) -> None:
    instrument.silent = True
    transport = ScpiTransport("127.0.0.1", instrument.port, timeout=0.4, retries=0)
    transport.connect()
    try:
        with pytest.raises((TimeoutError, ConnectionError)):
            transport.request("*IDN?")
    finally:
        transport.close()


def test_oversized_response_is_rejected(instrument: LoopbackInstrument) -> None:
    """The size bound is now enforced by the core's read rather than per byte."""
    transport = ScpiTransport(
        "127.0.0.1", instrument.port, timeout=1.0, retries=0, max_response_bytes=4
    )
    transport.connect()
    try:
        with pytest.raises((ScpiError, ConnectionError, TimeoutError)):
            transport.request("*IDN?")
    finally:
        transport.close()


# -- the greeting, which must tolerate silence -----------------------------


def test_a_greeting_is_consumed_when_the_instrument_sends_one() -> None:
    server = LoopbackInstrument(greeting=b"E-Resistor ready\n")
    try:
        transport = ScpiTransport("127.0.0.1", server.port, timeout=1.0, read_greeting=True)
        transport.connect()
        try:
            # The banner must not be mistaken for the reply to the first query.
            assert transport.request("*IDN?") == "ERESISTOR,ER-1,SN001,1.2.3"
        finally:
            transport.close()
    finally:
        server.close()


def test_a_silent_instrument_still_connects(instrument: LoopbackInstrument) -> None:
    """No banner is the normal case, and a greeting timeout must not break the link."""
    transport = ScpiTransport(
        "127.0.0.1", instrument.port, timeout=1.0, read_greeting=True, greeting_timeout_s=0.2
    )
    transport.connect()
    try:
        assert transport.state is ConnectionState.CONNECTED
        assert transport.request("*IDN?") == "ERESISTOR,ER-1,SN001,1.2.3"
    finally:
        transport.close()


def test_the_greeting_read_can_be_skipped(instrument: LoopbackInstrument) -> None:
    transport = ScpiTransport("127.0.0.1", instrument.port, timeout=1.0, read_greeting=False)
    transport.connect()
    try:
        assert transport.request("*IDN?") == "ERESISTOR,ER-1,SN001,1.2.3"
    finally:
        transport.close()


# -- reconnect policy stayed in the driver ---------------------------------


def test_reconnect_opens_a_new_connection(instrument: LoopbackInstrument) -> None:
    transport = connected(instrument)
    try:
        before = instrument.connections
        transport.reconnect()
        assert instrument.connections > before
        assert transport.state is ConnectionState.CONNECTED
    finally:
        transport.close()


def test_state_callback_observes_transitions(instrument: LoopbackInstrument) -> None:
    seen: list[ConnectionState] = []
    transport = ScpiTransport(
        "127.0.0.1", instrument.port, timeout=1.0, state_callback=seen.append
    )
    transport.connect()
    transport.close()
    assert ConnectionState.CONNECTED in seen
    assert ConnectionState.DISCONNECTED in seen
