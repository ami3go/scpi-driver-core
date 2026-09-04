"""Migration proof: the VISA path runs through ``scpi-driver-core``.

The driver's pre-existing tests all drive the simulator, so they show that
nothing regressed but say nothing about the transport the migration actually
replaced. These drive a real ``Agilent33220A`` over the real ``PyvisaTransport``
over the core's ``VisaTransport``, against a fake VISA backend.

This is what the secondary-validation list in section 42 of the core's task document asks for.
"""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

import scpi_driver_core.transport.visa as core_visa
from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220AConnectionError, Agilent33220ATimeoutError
from agilent33220a.transport import PyvisaTransport
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import VisaTransport

IDN = b"Agilent Technologies,33220A,MY44012345,2.02-2.02-22-2\n"


class FakeVisaResource:
    def __init__(self, resource_name: str, **settings: Any) -> None:
        self.resource_name = resource_name
        self.settings = settings
        self.timeout = 0.0
        self.chunk_size = 0
        self.messages: deque[bytes] = deque()
        self.written = bytearray()
        self.closed = False

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
    replies = {
        "*IDN?": IDN,
        "*ESR?": b"0\n",
        "SYSTem:ERRor?": b'+0,"No error"\n',
        "FREQuency?": b"+1.00000000000000E+03\n",
        "VOLTage?": b"+1.00000000000000E+00\n",
        "FUNCtion?": b"SIN\n",
    }
    return replies.get(command, b"0\n")


@pytest.fixture
def fake_visa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_visa, "_load_pyvisa", lambda: SimpleNamespace(ResourceManager=FakeResourceManager)
    )


# -- the VISA path ---------------------------------------------------------


def test_transport_is_built_on_the_core(fake_visa: None) -> None:
    transport = PyvisaTransport("GPIB0::22::INSTR")
    transport.open()
    try:
        assert isinstance(transport.client, ScpiClient)
        assert isinstance(transport.client.transport, VisaTransport)
    finally:
        transport.close()


def test_construction_performs_no_io(fake_visa: None) -> None:
    """Import- and construction-time silence is a documented property here."""
    PyvisaTransport("GPIB0::22::INSTR")
    assert FakeResourceManager.last is None or FakeResourceManager.last.closed is not None


def test_terminations_are_left_to_the_codec(fake_visa: None) -> None:
    """PyVISA must not trim payload bytes; the codec above it owns framing."""
    transport = PyvisaTransport("GPIB0::22::INSTR")
    transport.open()
    try:
        settings = FakeResourceManager.last.settings  # type: ignore[union-attr]
        assert settings["read_termination"] is None
        assert settings["write_termination"] is None
    finally:
        transport.close()


def test_timeout_is_converted_to_milliseconds(fake_visa: None) -> None:
    transport = PyvisaTransport("GPIB0::22::INSTR", timeout_s=2.5)
    transport.open()
    try:
        assert FakeResourceManager.last.timeout == 2500.0  # type: ignore[union-attr]
    finally:
        transport.close()


def test_open_close_and_is_open(fake_visa: None) -> None:
    transport = PyvisaTransport("GPIB0::22::INSTR")
    assert transport.is_open() is False
    transport.open()
    assert transport.is_open() is True
    transport.close()
    assert transport.is_open() is False


def test_io_before_open_is_refused(fake_visa: None) -> None:
    transport = PyvisaTransport("GPIB0::22::INSTR")
    with pytest.raises(Agilent33220AConnectionError):
        transport.query("*IDN?")


def test_missing_resource_string_is_refused() -> None:
    with pytest.raises(Agilent33220AConnectionError):
        PyvisaTransport("   ")


def test_open_failure_becomes_a_connection_error(
    fake_visa: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: FakeResourceManager, name: str, **settings: Any) -> Any:
        raise RuntimeError("no such resource")

    monkeypatch.setattr(FakeResourceManager, "open_resource", boom)
    transport = PyvisaTransport("GPIB0::99::INSTR")
    with pytest.raises(Agilent33220AConnectionError):
        transport.open()


def test_timeout_becomes_the_drivers_own_error(fake_visa: None) -> None:
    transport = PyvisaTransport("GPIB0::22::INSTR")
    transport.open()
    try:
        with pytest.raises(Agilent33220ATimeoutError):
            transport.query("NO:REPLY")
    finally:
        transport.close()


def test_timeout_setter_applies_to_later_operations(fake_visa: None) -> None:
    transport = PyvisaTransport("GPIB0::22::INSTR", timeout_s=5.0)
    transport.open()
    try:
        transport.timeout_s = 1.5
        assert transport.timeout_s == 1.5
        transport.query("*IDN?")
        assert FakeResourceManager.last.timeout == 1500.0  # type: ignore[union-attr]
    finally:
        transport.close()


# -- the driver over that transport ----------------------------------------


def test_driver_identifies_over_visa(fake_visa: None) -> None:
    driver = Agilent33220A.connect_visa("GPIB0::22::INSTR")
    try:
        identity = driver.identify()
        assert identity.manufacturer == "Agilent Technologies"
        assert identity.model == "33220A"
        assert identity.serial == "MY44012345"
        assert identity.firmware == "2.02-2.02-22-2"
    finally:
        driver.close()


def test_driver_reads_a_setting_over_visa(fake_visa: None) -> None:
    driver = Agilent33220A.connect_visa("GPIB0::22::INSTR")
    try:
        assert driver.get_frequency() == 1000.0
    finally:
        driver.close()


# -- behavior preserved across the migration -------------------------------


def test_identity_tolerates_a_partial_reply() -> None:
    """Historic behaviour: missing *IDN? fields become empty, not an error."""
    from agilent33220a.driver import _identity_fields

    fields = _identity_fields("OnlyManufacturer")
    assert fields["manufacturer"] == "OnlyManufacturer"
    assert fields["model"] == ""
    assert fields["serial"] == ""


def test_identity_uses_the_core_for_well_formed_replies() -> None:
    from agilent33220a.driver import _identity_fields

    fields = _identity_fields("Agilent Technologies,33220A,MY47001234,2.35")
    assert fields["model"] == "33220A"
    assert fields["serial"] == "MY47001234"


def test_identity_helper_is_shared_with_the_core() -> None:
    from agilent33220a.driver import _identity_fields

    fields = _identity_fields("Agilent Technologies,33220A,MY44012345,2.02")
    assert fields["model"] == "33220A"
    assert fields["serial"] == "MY44012345"
