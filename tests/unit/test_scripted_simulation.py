from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ResponseParseError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.models import ScpiError
from scpi_driver_core.scpi import ScpiClient, ScpiErrorQueue, ScpiTextCodec
from scpi_driver_core.scpi.ieee488 import Ieee4882
from scpi_driver_core.session import ScpiSession
from scpi_driver_core.simulation import ScriptedReply, ScriptedScpiTransport
from scpi_driver_core.transport import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    Transport,
    TransportState,
)

IDN = "KEYSIGHT,N6700C,MY56000102,D.01.09"


def instrument(**kwargs: object) -> ScriptedScpiTransport:
    transport = ScriptedScpiTransport(**kwargs)  # type: ignore[arg-type]
    transport.open()
    return transport


def client_for(transport: ScriptedScpiTransport) -> ScpiClient:
    return ScpiClient(transport)


# -- wiring ---------------------------------------------------------------


def test_satisfies_the_transport_protocol() -> None:
    assert isinstance(ScriptedScpiTransport(), Transport)


def test_requires_a_command_terminator() -> None:
    """Without one, consecutive commands could not be told apart."""
    with pytest.raises(ConfigurationError, match="terminator"):
        ScriptedScpiTransport(codec=ScpiTextCodec(command_terminator=b""))


def test_lifecycle_matches_the_transport_contract() -> None:
    transport = ScriptedScpiTransport()
    assert transport.state is TransportState.CREATED
    transport.open()
    assert transport.is_open is True
    transport.close()
    transport.close()
    assert transport.state is TransportState.CLOSED


def test_descriptor_identifies_the_simulation() -> None:
    assert ScriptedScpiTransport().descriptor.kind == "scripted"


# -- exact handlers -------------------------------------------------------


def test_exact_command_reply() -> None:
    transport = instrument()
    transport.on("*IDN?", IDN)
    assert client_for(transport).query("*IDN?") == IDN


def test_matching_ignores_case_and_padding_as_an_instrument_does() -> None:
    transport = instrument()
    transport.on("*idn?", IDN)
    assert client_for(transport).query("  *IDN?  ") == IDN


def test_registration_is_chainable() -> None:
    transport = instrument()
    transport.on("*IDN?", IDN).on("MEAS:VOLT?", "1.5")
    client = client_for(transport)
    assert client.query("*IDN?") == IDN
    assert client.query_float("MEAS:VOLT?") == 1.5


def test_a_later_registration_replaces_an_earlier_one() -> None:
    transport = instrument()
    transport.on("MEAS?", "1.0").on("MEAS?", "2.0")
    assert client_for(transport).query("MEAS?") == "2.0"


def test_a_command_with_no_reply_answers_nothing() -> None:
    transport = instrument()
    transport.on("*RST")
    client = client_for(transport)
    client.write("*RST")
    assert transport.history == ["*RST"]


# -- callable handlers ----------------------------------------------------


def test_handler_receives_the_command() -> None:
    transport = instrument()
    seen: list[str] = []

    def handler(command: str) -> str:
        seen.append(command)
        return "ok"

    transport.on("MEAS?", handler)
    client_for(transport).query("MEAS?")
    assert seen == ["MEAS?"]


def test_handler_can_model_state() -> None:
    """A simulator's physical model lives in its handlers, not in this class."""
    transport = instrument()
    voltage = {"value": 0.0}

    transport.on_regex(r"^VOLT (\S+)$", lambda cmd: _set(voltage, cmd))
    transport.on("VOLT?", lambda _cmd: f"{voltage['value']:.3f}")

    client = client_for(transport)
    client.write("VOLT 12.5")
    assert client.query_float("VOLT?") == 12.5


def _set(store: dict[str, float], command: str) -> None:
    store["value"] = float(command.split()[1])
    return None


# -- regex and predicate handlers -----------------------------------------


def test_regex_handler() -> None:
    transport = instrument()
    transport.on_regex(r"^MEAS:(VOLT|CURR)\?$", "1.5")
    client = client_for(transport)
    assert client.query("MEAS:VOLT?") == "1.5"
    assert client.query("MEAS:CURR?") == "1.5"


def test_regex_is_case_insensitive_by_default() -> None:
    transport = instrument()
    transport.on_regex(r"^meas\?$", "1.5")
    assert client_for(transport).query("MEAS?") == "1.5"


def test_predicate_handler() -> None:
    transport = instrument()
    transport.on_predicate(lambda command: command.endswith("?"), "42")
    assert client_for(transport).query("ANYTHING?") == "42"


def test_exact_handlers_win_over_patterns() -> None:
    transport = instrument()
    transport.on_regex(r".*", "pattern")
    transport.on("MEAS?", "exact")
    assert client_for(transport).query("MEAS?") == "exact"


def test_patterns_are_tried_in_registration_order() -> None:
    transport = instrument()
    transport.on_regex(r"^MEAS", "first")
    transport.on_regex(r"\?$", "second")
    assert client_for(transport).query("MEAS?") == "first"


# -- binary replies -------------------------------------------------------


def test_raw_binary_reply_is_returned_byte_for_byte() -> None:
    transport = instrument()
    payload = bytes(range(256))
    transport.on("CURVE?", payload)
    client = client_for(transport)
    client.write("CURVE?")
    request = ReadRequest(mode=ReadMode.EXACT_LENGTH, length=len(payload))
    assert client.read_bytes(request) == payload


def test_binary_block_reply_round_trips_through_the_client() -> None:
    payload = bytes(range(256)) + b"\x00 \t trailing \x00"
    transport = instrument()
    transport.reply_block("CURVE?", payload)
    assert client_for(transport).query_binary_block("CURVE?") == payload


def test_block_helper_frames_a_payload() -> None:
    transport = ScriptedScpiTransport()
    assert transport.block(b"ABCD") == b"#14ABCD\n"


def test_a_scripted_block_can_be_handed_to_a_handler() -> None:
    transport = instrument()
    transport.on("CURVE?", lambda _cmd: transport.block(b"XY"))
    assert client_for(transport).query_binary_block("CURVE?") == b"XY"


# -- failure injection ----------------------------------------------------


def test_forced_timeout_on_the_next_read() -> None:
    transport = instrument()
    transport.on("SLOW?", ScriptedReply(raises=TransportTimeoutError("instrument is busy")))
    with pytest.raises(TransportTimeoutError):
        client_for(transport).query("SLOW?")


def test_forced_disconnect_faults_the_transport() -> None:
    transport = instrument()
    transport.on("BOOM", ScriptedReply(disconnect=True))
    client_for(transport).write("BOOM")
    assert transport.state is TransportState.FAULTED


def test_a_failure_that_also_disconnects() -> None:
    transport = instrument()
    transport.on("BOOM?", ScriptedReply(raises=TransportError("link lost"), disconnect=True))
    with pytest.raises(TransportError):
        client_for(transport).query("BOOM?")
    assert transport.state is TransportState.FAULTED


def test_malformed_response_surfaces_as_a_parse_error() -> None:
    """The simulator can answer nonsense, so drivers can be tested against it."""
    transport = instrument()
    transport.on("MEAS?", "not-a-number")
    with pytest.raises(ResponseParseError):
        client_for(transport).query_float("MEAS?")


def test_delayed_response_uses_the_injected_sleep() -> None:
    slept: list[float] = []
    transport = ScriptedScpiTransport(sleep=slept.append)
    transport.open()
    transport.on("SLOW?", ScriptedReply(data=b"1.5\n", delay_s=2.0))
    assert client_for(transport).query("SLOW?") == "1.5"
    assert slept == [2.0]


def test_byte_level_injection_remains_available() -> None:
    transport = instrument()
    transport.on("MEAS?", "1.5")
    transport.inner.fail_next_read(TransportError("cable"), fault=False)
    with pytest.raises(TransportError):
        client_for(transport).query("MEAS?")


# -- the simulated error queue --------------------------------------------


def test_error_query_reports_no_error_when_clean() -> None:
    transport = instrument()
    transport.on("*RST")
    client = client_for(transport)
    client.write("*RST")
    assert ScpiErrorQueue(client).drain() == []


def test_an_unknown_command_queues_an_undefined_header_error() -> None:
    """Just as a real instrument does, rather than failing silently."""
    transport = instrument()
    client = client_for(transport)
    client.write("NOSUCHCOMMAND")
    errors = ScpiErrorQueue(client).drain()
    assert [error.code for error in errors] == [-113]


def test_errors_are_reported_in_order_then_the_queue_empties() -> None:
    transport = instrument()
    transport.push_error(ScpiError(code=-222, message="Data out of range", raw=""))
    transport.push_error(ScpiError(code=-113, message="Undefined header", raw=""))
    queue = ScpiErrorQueue(client_for(transport))
    assert [error.code for error in queue.drain()] == [-222, -113]
    assert queue.drain() == []


def test_pending_errors_are_inspectable() -> None:
    transport = instrument()
    transport.push_error(ScpiError(code=-100, message="Command error", raw=""))
    assert [error.code for error in transport.pending_errors] == [-100]


def test_unknown_command_errors_can_be_disabled() -> None:
    transport = ScriptedScpiTransport(unknown_command_error=None)
    transport.open()
    client = client_for(transport)
    client.write("NOSUCHCOMMAND")
    assert ScpiErrorQueue(client).drain() == []


def test_the_error_query_command_is_configurable() -> None:
    transport = ScriptedScpiTransport(error_query="SYSTEM:ERROR:NEXT?")
    transport.open()
    client = client_for(transport)
    assert client.query("SYSTEM:ERROR:NEXT?") == '0,"No error"'


# -- history --------------------------------------------------------------


def test_history_records_every_command() -> None:
    transport = instrument()
    transport.on("*IDN?", IDN).on("*RST")
    client = client_for(transport)
    client.write("*RST")
    client.query("*IDN?")
    assert transport.history == ["*RST", "*IDN?"]


def test_history_is_a_copy() -> None:
    transport = instrument()
    transport.on("*RST")
    client_for(transport).write("*RST")
    transport.history.append("TAMPERED")
    assert transport.history == ["*RST"]


def test_history_can_be_cleared() -> None:
    transport = instrument()
    transport.on("*RST")
    client_for(transport).write("*RST")
    transport.clear_history()
    assert transport.history == []


# -- realistic use --------------------------------------------------------


def test_it_drives_the_ieee488_helpers() -> None:
    transport = instrument()
    transport.on("*IDN?", IDN).on("*OPC?", "1").on("*TST?", "0").on("*CLS").on("*RST")
    ieee = Ieee4882(client_for(transport))

    identity = ieee.identify()
    assert identity.model == "N6700C"
    ieee.clear_status()
    ieee.reset()
    assert ieee.operation_complete() is True
    assert ieee.self_test().passed is True
    assert transport.history == ["*IDN?", "*CLS", "*RST", "*OPC?", "*TST?"]


def test_it_drives_a_full_session() -> None:
    transport = ScriptedScpiTransport()
    transport.on("*IDN?", IDN)
    session = ScpiSession("psu1", ScpiClient(transport))
    session.open(probe=True, validate_identity=lambda identity: None)
    assert session.is_connected is True
    assert session.health.communication_ok is True
    assert session.get_identity().manufacturer == "KEYSIGHT"
    session.close()


def test_a_session_probe_against_a_silent_instrument_fails_cleanly() -> None:
    transport = ScriptedScpiTransport(unknown_command_error=None)
    session = ScpiSession("psu1", ScpiClient(transport))
    with pytest.raises(TransportTimeoutError):
        session.open(probe=True)
    assert session.is_connected is False


# -- edges ----------------------------------------------------------------


def test_flush_discards_a_queued_reply() -> None:
    transport = instrument()
    transport.on("MEAS?", "1.5")
    client_for(transport).write("MEAS?")
    transport.flush(FlushDirection.INPUT)
    with pytest.raises(TransportTimeoutError):
        client_for(transport).read_bytes(ReadRequest(mode=ReadMode.UP_TO_LENGTH, length=16))


def test_an_unterminated_write_is_still_understood() -> None:
    """A caller writing raw bytes may omit the terminator; the command still lands."""
    transport = instrument()
    transport.on("*RST")
    transport.write(b"*RST")
    assert transport.history == ["*RST"]


def test_a_command_matching_no_registered_pattern_is_unknown() -> None:
    transport = instrument()
    transport.on_regex(r"^MEAS", "1.5")
    client = client_for(transport)
    client.write("OUTP ON")
    assert [error.code for error in ScpiErrorQueue(client).drain()] == [-113]


def test_a_reply_that_already_ends_with_the_terminator_is_not_doubled() -> None:
    transport = instrument()
    transport.on("MEAS?", "1.5\n")
    client = client_for(transport)
    assert client.query("MEAS?") == "1.5"
    assert transport.inner.pending_bytes == 0
