"""Migration proof: the USBTMC and binary-waveform paths run through the core.

This is the driver section 42B of the core's task document exists to validate:
IEEE-488.2 binary blocks, waveform transfers, and setup/file transfers. Sample
bytes routinely include 0x0A and 0x20, so the tests below deliberately use
payloads full of them — a single stray ``strip()`` anywhere in the stack would
corrupt a waveform, and these are the tests that would catch it.

The driver's pre-existing tests all drive the simulator, so they say nothing
about the transport the migration replaced.
"""

from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any

import pytest

import scpi_driver_core.transport.visa as core_visa
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import ReadMode, ReadRequest, VisaTransport
from tbs1000c.codec import build_ieee_block, parse_curve_response
from tbs1000c.exceptions import (
    Tbs1000cConnectionError,
    Tbs1000cProtocolError,
    Tbs1000cTimeoutError,
)
from tbs1000c.transport import PyvisaUsbtmcTransport

IDN = b"TEKTRONIX,TBS 1072C,CU10100,CF:91.1CT FV:v1.00\n"

#: Every byte value, so nothing in the stack may treat any of them as framing.
HOSTILE_WAVEFORM = bytes(range(256)) + b"\n\n\r\n   \t\x00\x00"


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
            pass  # models an instrument that simply does not answer
        elif command.startswith("CURVE?") or command.startswith("CURVe?"):
            self.messages.append(build_ieee_block(HOSTILE_WAVEFORM) + b"\n")
        elif "?" in command:
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
    return {"*IDN?": IDN, "*ESR?": b"0\n"}.get(command, b"0\n")


@pytest.fixture
def fake_visa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        core_visa, "_load_pyvisa", lambda: SimpleNamespace(ResourceManager=FakeResourceManager)
    )


def opened(resource: str = "USB0::0x0699::0x0368::C012345::INSTR") -> PyvisaUsbtmcTransport:
    transport = PyvisaUsbtmcTransport(resource)
    transport.open()
    return transport


# -- the USBTMC path -------------------------------------------------------


def test_transport_is_built_on_the_core(fake_visa: None) -> None:
    transport = opened()
    try:
        assert isinstance(transport.client, ScpiClient)
        assert isinstance(transport.client.transport, VisaTransport)
    finally:
        transport.close()


def test_usbtmc_resource_string_is_passed_through(fake_visa: None) -> None:
    transport = opened()
    try:
        assert FakeResourceManager.last.resource_name.startswith("USB0::")  # type: ignore[union-attr]
    finally:
        transport.close()


def test_terminations_are_disabled_so_samples_survive(fake_visa: None) -> None:
    """This is the setting that would silently corrupt a waveform if left on."""
    transport = opened()
    try:
        settings = FakeResourceManager.last.settings  # type: ignore[union-attr]
        assert settings["read_termination"] is None
        assert settings["write_termination"] is None
    finally:
        transport.close()


def test_text_query_still_works(fake_visa: None) -> None:
    transport = opened()
    try:
        assert transport.query("*IDN?") == "TEKTRONIX,TBS 1072C,CU10100,CF:91.1CT FV:v1.00"
    finally:
        transport.close()


def test_io_before_open_is_refused(fake_visa: None) -> None:
    transport = PyvisaUsbtmcTransport("USB0::0x0699::0x0368::C012345::INSTR")
    with pytest.raises(Tbs1000cConnectionError):
        transport.query_binary("CURVE?")


def test_missing_resource_string_is_refused() -> None:
    with pytest.raises(Tbs1000cConnectionError):
        PyvisaUsbtmcTransport("  ")


def test_open_failure_becomes_a_connection_error(
    fake_visa: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: FakeResourceManager, name: str, **settings: Any) -> Any:
        raise RuntimeError("device not found")

    monkeypatch.setattr(FakeResourceManager, "open_resource", boom)
    with pytest.raises(Tbs1000cConnectionError):
        opened()


def test_timeout_becomes_the_drivers_own_error(fake_visa: None) -> None:
    transport = opened()
    try:
        with pytest.raises(Tbs1000cTimeoutError):
            transport.query_binary("SILENT:QUERY?")
    finally:
        transport.close()


# -- waveform transfer, byte for byte --------------------------------------


def test_curve_query_returns_every_sample_byte_intact(fake_visa: None) -> None:
    transport = opened()
    try:
        raw = transport.query_binary("CURVE?")
        assert parse_curve_response(raw) == HOSTILE_WAVEFORM
    finally:
        transport.close()


def test_a_waveform_of_newlines_alone_survives(fake_visa: None) -> None:
    """0x0A is both the terminator and a legitimate sample value."""
    payload = b"\n" * 64
    transport = opened()
    try:
        FakeResourceManager.last.messages.append(  # type: ignore[union-attr]
            build_ieee_block(payload) + b"\n"
        )
        request = ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)
        raw = transport.client.read_bytes(request)  # type: ignore[union-attr]
        assert parse_curve_response(raw) == payload
    finally:
        transport.close()


def test_binary_write_frames_prefix_block_and_terminator(fake_visa: None) -> None:
    transport = opened()
    try:
        payload = b"setup\ndata\x00"
        transport.write_binary("FILESystem:WRITEFile ", build_ieee_block(payload))
        written = bytes(FakeResourceManager.last.written)  # type: ignore[union-attr]
        assert written.startswith(b"FILESystem:WRITEFile #")
        assert written.endswith(b"\n")
        body = written[len(b"FILESystem:WRITEFile ") : -1]
        assert parse_curve_response(body) == payload
    finally:
        transport.close()


def test_binary_write_does_not_drop_a_terminator_when_the_payload_ends_in_one(
    fake_visa: None,
) -> None:
    """The block ends with 0x0A; the command terminator must still be appended."""
    transport = opened()
    try:
        transport.write_binary("FILESystem:WRITEFile ", build_ieee_block(b"ab\n"))
        written = bytes(FakeResourceManager.last.written)  # type: ignore[union-attr]
        assert written.endswith(b"#13ab\n\n")
    finally:
        transport.close()


# -- codec behavior preserved ----------------------------------------------


def test_block_encoding_is_unchanged() -> None:
    assert build_ieee_block(b"") == b"#10"
    assert build_ieee_block(b"ABCD") == b"#14ABCD"
    assert build_ieee_block(bytes(256)) == b"#3256" + bytes(256)


def test_block_round_trip_through_the_core() -> None:
    assert parse_curve_response(build_ieee_block(HOSTILE_WAVEFORM)) == HOSTILE_WAVEFORM


def test_trailing_terminator_after_the_block_is_ignored() -> None:
    assert parse_curve_response(build_ieee_block(b"\x01\x02") + b"\n") == b"\x01\x02"


def test_truncated_block_is_reported() -> None:
    with pytest.raises(Tbs1000cProtocolError):
        parse_curve_response(b"#18AB")


def test_malformed_block_header_is_reported() -> None:
    with pytest.raises(Tbs1000cProtocolError):
        parse_curve_response(b"#X4ABCD")


def test_ascii_form_is_still_supported() -> None:
    """The dual-format handling is this instrument's, and stayed here."""
    assert parse_curve_response(b"1,2,-3\n") == bytes([1, 2, 0xFD])


def test_identity_parsing_still_tolerates_a_short_reply() -> None:
    from tbs1000c.codec import parse_idn

    identity = parse_idn("TEKTRONIX,TBS 1072C")
    assert identity.manufacturer == "TEKTRONIX"
    assert identity.model == "TBS 1072C"
    assert identity.serial == ""
