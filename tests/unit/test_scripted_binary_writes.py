"""CORE-ARB-B: scripted outbound IEEE-488.2 binary upload contract."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from scpi_driver_core.exceptions import (
    ProtocolError,
    TransportError,
    UnsupportedOperationError,
)
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.simulation import ScriptedScpiTransport
from scpi_driver_core.transport import TransportState


@pytest.mark.parametrize(
    "payload",
    [b"", bytes(range(256)), b"\x00\n\r;#\xff\xfe\x00", b"\x00" * 100_000],
)
def test_binary_upload_preserves_every_byte(payload: bytes) -> None:
    transport = ScriptedScpiTransport()
    transport.open()
    seen: list[bytes] = []
    transport.on_binary_write("DATA:ARB", lambda _prefix, raw: seen.append(raw))
    ScpiClient(transport).write_binary_block("DATA:ARB ", payload)
    assert seen == [payload]
    assert transport.binary_history == [("DATA:ARB", payload)]
    assert transport.history == []
    transport.binary_history.clear()
    assert transport.binary_history == [("DATA:ARB", payload)]
    transport.clear_history()
    assert transport.binary_history == []


@pytest.mark.property
@given(st.binary(max_size=4096))
@settings(max_examples=120)
def test_binary_upload_property_round_trip(payload: bytes) -> None:
    transport = ScriptedScpiTransport()
    transport.on_binary_write("DATA:ARB", lambda _prefix, _raw: None)
    transport.open()
    ScpiClient(transport).write_binary_block("DATA:ARB ", payload)
    assert transport.binary_history[0][1] == payload
    assert transport.state is TransportState.OPEN


def test_binary_and_text_commands_do_not_interfere() -> None:
    transport = ScriptedScpiTransport()
    transport.open()
    transport.on_binary_write("DATA:ARB", lambda _prefix, _raw: None)
    transport.on("OUTP ON")
    transport.on("MEAS?", "1")
    client = ScpiClient(transport)
    client.write("OUTP ON")
    client.write_binary_block("DATA:ARB ", b";\n\r#\x00\xff")
    assert client.query_int("MEAS?") == 1
    assert transport.history == ["OUTP ON", "MEAS?"]
    assert transport.binary_history[0][1] == b";\n\r#\x00\xff"


def test_compound_commands_resume_after_exact_declared_length() -> None:
    transport = ScriptedScpiTransport()
    transport.open()
    transport.on_binary_write("DATA:ARB", lambda _prefix, _raw: None)
    transport.on("OUTP ON")
    transport.write(b"DATA:ARB #14;\n#A;:OUTP ON\n")
    assert transport.binary_history == [("DATA:ARB", b";\n#A")]
    assert transport.history == ["OUTP ON"]


@pytest.mark.parametrize(
    ("raw", "exception"),
    [
        (b"DATA:ARB #", ProtocolError),
        (b"DATA:ARB #Xabc", ProtocolError),
        (b"DATA:ARB #0abc\n", UnsupportedOperationError),
        (b"DATA:ARB #3x12aaa\n", ProtocolError),
        (b"DATA:ARB #312", ProtocolError),
        (b"DATA:ARB #15hi\n", ProtocolError),
        (b"DATA:ARB #12abjunk\n", ProtocolError),
        (b"DATA:ARB #9100000000", ProtocolError),
    ],
)
def test_malformed_binary_faults(raw: bytes, exception: type[Exception]) -> None:
    transport = ScriptedScpiTransport()
    transport.open()
    with pytest.raises(exception):
        transport.write(raw)
    assert transport.state is TransportState.FAULTED


def test_injected_write_error_faults_without_handler_replay() -> None:
    transport = ScriptedScpiTransport()
    transport.open()
    seen: list[bytes] = []
    transport.on_binary_write("DATA:ARB", lambda _prefix, raw: seen.append(raw))
    transport.inner.fail_next_write(TransportError("cable loss"), fault=False)
    with pytest.raises(TransportError):
        ScpiClient(transport).write_binary_block("DATA:ARB ", b"test")
    assert transport.state is TransportState.FAULTED
    assert seen == []


def test_handler_exception_faults() -> None:
    transport = ScriptedScpiTransport()
    transport.open()

    def bad_handler(_command: str, _payload: bytes) -> None:
        raise ValueError("injected callback failure")

    transport.on_binary_write("DATA:ARB", bad_handler)
    with pytest.raises(ValueError):
        ScpiClient(transport).write_binary_block("DATA:ARB ", b"abc")
    assert transport.state is TransportState.FAULTED


@pytest.mark.timeout(5)
@pytest.mark.watchdog
def test_concurrent_binary_uploads_are_serialized() -> None:
    transport = ScriptedScpiTransport()
    transport.open()
    seen: list[bytes] = []
    transport.on_binary_write("DATA:ARB", lambda _prefix, raw: seen.append(raw))
    client = ScpiClient(transport)
    payloads = [bytes([index]) * 1000 for index in range(20)]
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda payload: client.write_binary_block("DATA:ARB ", payload), payloads))
    assert sorted(seen) == sorted(payloads)
    assert sorted(value for _, value in transport.binary_history) == sorted(payloads)
