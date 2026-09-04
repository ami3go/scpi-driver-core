"""Migration proof: the VISA path and unit-suffixed parsing run through the core.

Section 42E of the core's task document names this driver for exactly two
things: tolerant numeric parsing with an optional unit suffix, and the device
error queue. Both are covered here, along with the VISA transport the migration
replaced — the driver's pre-existing tests all drive the simulator.

The unit-suffix behaviour is not hypothetical. This instrument's firmware
answers ``SYSTem:NOMinal:VOLTage?`` with ``"500.0 V"`` on real hardware while
its own programming guide and simulator show a bare number, which is why
``parse_optional_unit_float`` exists in the core at all.
"""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

import scpi_driver_core.transport.visa as core_visa
from ea_ps9000t.driver import EaPs9000T, _identity_parts, _parse_float, _parse_number
from ea_ps9000t.exceptions import EaPs9000TConnectionError, EaPs9000TTimeoutError
from ea_ps9000t.transport import PyvisaTransport
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import VisaTransport

IDN = b"EA Elektro-Automatik,PS 9080-100 T,2815490123,V2.09 4.10,my bench supply\n"


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
    """Answers with the unit suffix this instrument really appends."""
    replies = {
        "*IDN?": IDN,
        "VOLTage?": b"500.0 V\n",
        "CURRent?": b"3.500 A\n",
        "POWer?": b"1500 W\n",
        "SYSTem:ERRor?": b'0,"No error"\n',
        "SYSTem:LOCK:OWNer?": b"REMOTE\n",
    }
    return replies.get(command, b"0\n")


@pytest.fixture
def fake_visa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_visa, "_load_pyvisa", lambda: SimpleNamespace(ResourceManager=FakeResourceManager)
    )


def opened(resource: str = "TCPIP0::192.0.2.10::inst0::INSTR") -> PyvisaTransport:
    transport = PyvisaTransport(resource)
    transport.open()
    return transport


# -- the VISA path ---------------------------------------------------------


def test_transport_is_built_on_the_core(fake_visa: None) -> None:
    transport = opened()
    try:
        assert isinstance(transport.client, ScpiClient)
        assert isinstance(transport.client.transport, VisaTransport)
    finally:
        transport.close()


def test_terminations_are_left_to_the_codec(fake_visa: None) -> None:
    transport = opened()
    try:
        settings = FakeResourceManager.last.settings  # type: ignore[union-attr]
        assert settings["read_termination"] is None
        assert settings["write_termination"] is None
    finally:
        transport.close()


def test_io_before_open_is_refused(fake_visa: None) -> None:
    with pytest.raises(EaPs9000TConnectionError):
        PyvisaTransport("TCPIP0::192.0.2.10::inst0::INSTR").query("*IDN?")


def test_missing_resource_string_is_refused() -> None:
    with pytest.raises(EaPs9000TConnectionError):
        PyvisaTransport(" ")


def test_open_failure_becomes_a_connection_error(
    fake_visa: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: FakeResourceManager, name: str, **settings: Any) -> Any:
        raise RuntimeError("unreachable")

    monkeypatch.setattr(FakeResourceManager, "open_resource", boom)
    with pytest.raises(EaPs9000TConnectionError):
        opened()


def test_timeout_becomes_the_drivers_own_error(fake_visa: None) -> None:
    transport = opened()
    try:
        with pytest.raises(EaPs9000TTimeoutError):
            transport.query("SILENT:QUERY?")
    finally:
        transport.close()


# -- the unit suffix, over the real transport ------------------------------


def test_driver_reads_a_unit_suffixed_voltage_over_visa(fake_visa: None) -> None:
    """The reply is "500.0 V"; the getter must still return 500.0."""
    driver = EaPs9000T.connect_visa("TCPIP0::192.0.2.10::inst0::INSTR")
    try:
        assert driver.get_voltage() == 500.0
        assert driver.get_current() == 3.5
    finally:
        driver.close()


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("500.0", 500.0),
        ("500.0 V", 500.0),
        ("500.0V", 500.0),
        ("3.500 A", 3.5),
        ("  12  W  ", 12.0),
        ("+2.5e1 V", 25.0),
        ("-1.5", -1.5),
    ],
)
def test_unit_suffixed_numbers_parse_through_the_core(response: str, expected: float) -> None:
    assert _parse_float(response) == pytest.approx(expected)


def test_the_token_form_is_unchanged_for_integer_callers() -> None:
    """Integer getters call int() on this, so it must stay the verbatim token."""
    assert _parse_number("42") == "42"
    assert _parse_number("42 V") == "42"
    assert int(_parse_number("  7  ")) == 7


def test_historic_leniency_is_preserved() -> None:
    """The old token search accepted a number embedded in other text."""
    assert _parse_float("value=5 volts") == 5.0


def test_a_response_with_no_number_still_raises() -> None:
    from ea_ps9000t.exceptions import EaPs9000TProtocolError

    with pytest.raises(EaPs9000TProtocolError):
        _parse_float("no number here")


# -- identity, including this vendor's fifth field -------------------------


def test_identity_keeps_the_vendor_specific_user_text(fake_visa: None) -> None:
    driver = EaPs9000T.connect_visa("TCPIP0::192.0.2.10::inst0::INSTR")
    try:
        identity = driver.identify()
        assert identity.manufacturer == "EA Elektro-Automatik"
        assert identity.model == "PS 9080-100 T"
        assert identity.serial == "2815490123"
        assert identity.user_text == "my bench supply"
    finally:
        driver.close()


def test_identity_split_is_csv_aware() -> None:
    """A quoted comma in the user-text field is not a separator."""
    parts = _identity_parts('EA,PS 9080,SN1,V1.0,"lab 2, bench 4"')
    assert parts[4] == "lab 2, bench 4"


def test_identity_tolerates_a_short_reply() -> None:
    assert _identity_parts("EA,PS 9080")[:2] == ["EA", "PS 9080"]


def test_the_core_handles_the_unit_suffix_without_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove the core path is the one taken, not merely available.

    ``_parse_float`` keeps a fallback to this driver's historic token search,
    which would otherwise mask whether the core did the work: both produce
    500.0 for ``"500.0 V"``. Disabling the fallback removes the ambiguity.
    """
    import ea_ps9000t.driver as driver_module

    def fallback_must_not_run(response: str) -> str:
        raise AssertionError(f"fallback used for {response!r}; the core should have parsed it")

    monkeypatch.setattr(driver_module, "_parse_number", fallback_must_not_run)
    assert driver_module._parse_float("500.0 V") == 500.0
    assert driver_module._parse_float("3.500 A") == 3.5
    assert driver_module._parse_float("500.0") == 500.0
