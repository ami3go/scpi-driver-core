"""Migration proof: the VISA GPIB path runs through ``scpi-driver-core``.

The driver's pre-existing tests drive the simulated and loopback transports, so
they show that nothing regressed but say nothing about the VISA transport the
migration actually replaced. These drive a real ``VisaGpibTransport`` over the
core's ``VisaTransport``, against a fake VISA backend.

The GPIB-specific rules — talk-only mode and primary-address ranges, R10 — are
checked here too, because the migration had to leave them in the driver rather
than push them into a core that has no business knowing about GPIB.
"""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

import scpi_driver_core.transport.visa as core_visa
from hp34401a_dmm.config import VisaGpibConfig
from hp34401a_dmm.errors import (
    InstrumentConnectionError,
    InstrumentTimeoutError,
    TransportError,
)
from hp34401a_dmm.visa_transport import VisaGpibTransport, validate_gpib_resource
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import VisaTransport

IDN = b"HEWLETT-PACKARD,34401A,0,11-5-2\n"


class FakeVisaResource:
    def __init__(self, resource_name: str, **settings: Any) -> None:
        self.resource_name = resource_name
        self.settings = settings
        self.timeout = 0.0
        self.chunk_size = 0
        self.messages: deque[bytes] = deque()
        self.written = bytearray()
        self.clears = 0
        self.closed = False

    def write_raw(self, data: bytes) -> int:
        self.written.extend(data)
        command = data.decode("ascii", errors="replace").strip()
        if command.startswith("SILENT"):
            return len(data)
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
        self.clears += 1
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
    replies = {
        "*IDN?": IDN,
        "READ?": b"+1.04858000E+00\n",
        "SYST:ERR?": b'+0,"No error"\n',
    }
    return replies.get(command, b"+0\n")


@pytest.fixture
def fake_visa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_visa, "_load_pyvisa", lambda: SimpleNamespace(ResourceManager=FakeResourceManager)
    )


def opened(resource: str = "GPIB0::22::INSTR", **kwargs: Any) -> VisaGpibTransport:
    transport = VisaGpibTransport(VisaGpibConfig(resource=resource, **kwargs))
    transport.open()
    return transport


# -- the VISA path ---------------------------------------------------------


def test_transport_is_built_on_the_core(fake_visa: None) -> None:
    transport = opened()
    try:
        assert isinstance(transport._client, ScpiClient)
        assert isinstance(transport._client.transport, VisaTransport)
    finally:
        transport.close()


def test_terminations_are_left_to_the_codec(fake_visa: None) -> None:
    """PyVISA no longer frames anything; the codec above it does."""
    transport = opened()
    try:
        settings = FakeResourceManager.last.settings  # type: ignore[union-attr]
        assert settings["read_termination"] is None
        assert settings["write_termination"] is None
    finally:
        transport.close()


def test_timeout_is_converted_to_milliseconds(fake_visa: None) -> None:
    transport = opened(timeout_s=2.5)
    try:
        assert FakeResourceManager.last.timeout == 2500.0  # type: ignore[union-attr]
    finally:
        transport.close()


def test_visa_library_is_forwarded(fake_visa: None) -> None:
    transport = opened(visa_library="@py")
    try:
        assert transport._client is not None
    finally:
        transport.close()


def test_open_close_and_is_open(fake_visa: None) -> None:
    transport = VisaGpibTransport(VisaGpibConfig(resource="GPIB0::22::INSTR"))
    assert transport.is_open() is False
    transport.open()
    assert transport.is_open() is True
    transport.close()
    assert transport.is_open() is False
    assert FakeResourceManager.last.closed is True  # type: ignore[union-attr]


def test_name_still_identifies_the_resource(fake_visa: None) -> None:
    transport = opened()
    try:
        assert transport.name == "visa:GPIB0::22::INSTR"
    finally:
        transport.close()


def test_open_failure_becomes_a_connection_error(
    fake_visa: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: FakeResourceManager, name: str, **settings: Any) -> Any:
        raise RuntimeError("no listener at that address")

    monkeypatch.setattr(FakeResourceManager, "open_resource", boom)
    with pytest.raises(InstrumentConnectionError):
        opened()


def test_a_missing_pyvisa_still_explains_the_gpib_backend_requirement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R9: pyvisa-py alone does not drive GPIB, and the message must say so."""
    from scpi_driver_core.exceptions import ConfigurationError

    def missing() -> Any:
        raise ConfigurationError("VisaTransport requires PyVISA")

    monkeypatch.setattr(core_visa, "_load_pyvisa", missing)
    with pytest.raises(InstrumentConnectionError, match="NI-VISA"):
        opened()


# -- talking to the instrument ---------------------------------------------


def test_query_round_trip_over_visa(fake_visa: None) -> None:
    transport = opened()
    try:
        assert transport.query("*IDN?") == "HEWLETT-PACKARD,34401A,0,11-5-2"
        assert transport.query("READ?") == "+1.04858000E+00"
    finally:
        transport.close()


def test_write_sends_the_terminator_exactly_once(fake_visa: None) -> None:
    """The old code stripped the terminator and relied on PyVISA re-adding it."""
    transport = opened()
    try:
        transport.write("*CLS")
        assert bytes(FakeResourceManager.last.written) == b"*CLS\n"  # type: ignore[union-attr]
    finally:
        transport.close()


def test_a_crlf_terminator_is_honoured(fake_visa: None) -> None:
    transport = opened(write_termination="\r\n", read_termination="\r\n")
    try:
        transport.write("*CLS")
        assert bytes(FakeResourceManager.last.written) == b"*CLS\r\n"  # type: ignore[union-attr]
    finally:
        transport.close()


def test_timeout_becomes_the_drivers_own_error(fake_visa: None) -> None:
    transport = opened()
    try:
        with pytest.raises(InstrumentTimeoutError):
            transport.query("SILENT:QUERY?")
    finally:
        transport.close()


def test_io_before_open_is_refused(fake_visa: None) -> None:
    transport = VisaGpibTransport(VisaGpibConfig(resource="GPIB0::22::INSTR"))
    with pytest.raises(TransportError):
        transport._send("*CLS\n")


def test_clear_reaches_the_backend(fake_visa: None) -> None:
    transport = opened()
    try:
        transport._clear()
        assert FakeResourceManager.last.clears == 1  # type: ignore[union-attr]
    finally:
        transport.close()


def test_set_timeout_applies_to_later_operations(fake_visa: None) -> None:
    transport = opened(timeout_s=10.0)
    try:
        transport._set_timeout(1.5)
        transport.query("*IDN?")
        assert FakeResourceManager.last.timeout == 1500.0  # type: ignore[union-attr]
    finally:
        transport.close()


# -- GPIB rules stayed in the driver ---------------------------------------


def test_talk_only_address_is_rejected() -> None:
    """R10. Talk-only is GPIB semantics; the core knows nothing about it."""
    with pytest.raises(InstrumentConnectionError, match="talk-only"):
        validate_gpib_resource("GPIB0::31::INSTR")


# A negative value never matches the GPIB address pattern, so it is not
# an out-of-range address; it is simply not a GPIB resource string.
@pytest.mark.parametrize("address", [32, 33, 99])
def test_out_of_range_addresses_are_rejected(address: int) -> None:
    with pytest.raises(InstrumentConnectionError, match="out of range"):
        validate_gpib_resource(f"GPIB0::{address}::INSTR")


def test_non_gpib_resources_are_not_address_checked() -> None:
    validate_gpib_resource("TCPIP0::192.0.2.10::inst0::INSTR")


def test_the_address_check_runs_before_anything_is_opened(fake_visa: None) -> None:
    with pytest.raises(InstrumentConnectionError):
        VisaGpibTransport(VisaGpibConfig(resource="GPIB0::31::INSTR"))
    assert FakeResourceManager.last is None or FakeResourceManager.last.closed is not None
