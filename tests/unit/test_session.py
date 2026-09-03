from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    IdentityError,
    TransportError,
)
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.session.session import ScpiSession
from scpi_driver_core.transport import MockTransport, TransportState

IDN = b"KEYSIGHT,N6700C,MY56000102,D.01.09\n"


def make(*replies: bytes, alias: str = "default") -> tuple[ScpiSession, MockTransport]:
    transport = MockTransport()
    for reply in replies:
        transport.feed(reply)
    return ScpiSession(alias, ScpiClient(transport)), transport


# -- construction ---------------------------------------------------------


def test_construction_performs_no_io() -> None:
    session, transport = make()
    assert transport.state is TransportState.CREATED
    assert transport.written == b""
    assert session.generation == 0


def test_exposes_its_parts() -> None:
    session, transport = make(alias="psu1")
    assert session.alias == "psu1"
    assert session.transport is transport
    assert session.ieee488.client is session.client


# -- transport state versus communication health --------------------------


def test_is_connected_reflects_the_transport_only() -> None:
    session, transport = make()
    assert session.is_connected is False
    transport.open()
    assert session.is_connected is True


def test_is_connected_performs_no_device_io() -> None:
    """Checking connectivity must never put bytes on the wire."""
    session, transport = make()
    transport.open()
    assert session.is_connected is True
    assert transport.written == b""


def test_health_starts_unknown() -> None:
    session, _ = make()
    assert session.health.connected is False
    assert session.health.communication_ok is None


def test_opening_does_not_claim_the_instrument_replies() -> None:
    """Holding a resource is not evidence that anything answers on it."""
    session, _ = make()
    session.open()
    assert session.health.connected is True
    assert session.health.communication_ok is None


def test_an_open_transport_can_report_bad_communication() -> None:
    """A powered-down instrument on a live connection is open and mute."""
    session, transport = make()
    session.open()
    transport.fail_next_read(TransportError("no reply"), fault=False)
    assert session.check_communication() is False
    assert session.is_connected is True
    assert session.health.connected is True
    assert session.health.communication_ok is False


def test_check_communication_records_success() -> None:
    session, transport = make(IDN)
    session.open()
    assert session.check_communication() is True
    assert session.health.communication_ok is True
    assert session.health.last_success_monotonic is not None
    assert transport.written == b"*IDN?\n"


def test_check_communication_records_the_reason_for_failure() -> None:
    session, transport = make()
    session.open()
    transport.fail_next_read(TransportError("cable pulled"), fault=False)
    session.check_communication()
    assert isinstance(session.health.last_error, TransportError)
    assert session.health.last_failure_monotonic is not None


def test_health_query_is_selectable_by_the_driver() -> None:
    transport = MockTransport()
    transport.feed(b"1\n")
    session = ScpiSession("default", ScpiClient(transport), health_query="SYST:VERS?")
    session.open()
    session.check_communication()
    assert transport.written == b"SYST:VERS?\n"


# -- generations ----------------------------------------------------------


def test_generation_advances_on_every_open() -> None:
    session, _ = make()
    session.open()
    assert session.generation == 1
    session.close()
    session.open()
    assert session.generation == 2


def test_generation_lets_a_reader_detect_a_reconnect() -> None:
    session, _ = make()
    session.open()
    observed = session.generation
    session.close()
    session.open()
    assert session.generation != observed


# -- identity cache -------------------------------------------------------


def test_identity_is_queried_once_and_cached() -> None:
    session, transport = make(IDN)
    session.open()
    first = session.get_identity()
    second = session.get_identity()
    assert first is second
    assert transport.written == b"*IDN?\n"


def test_identity_can_be_refreshed() -> None:
    session, transport = make(IDN, IDN)
    session.open()
    session.get_identity()
    session.get_identity(refresh=True)
    assert transport.written == b"*IDN?\n" * 2


def test_identity_cache_is_dropped_on_close() -> None:
    """A cached identity must never describe a previous connection."""
    session, transport = make(IDN)
    session.open()
    session.get_identity()
    session.close()
    transport.feed(IDN)  # closing discards buffered data, as a real transport does
    session.open()
    session.get_identity()
    assert transport.written == b"*IDN?\n" * 2


def test_identity_updates_health() -> None:
    session, _ = make(IDN)
    session.open()
    session.get_identity()
    assert session.health.communication_ok is True


# -- opening with a probe and validation ----------------------------------


def test_open_without_probe_sends_nothing() -> None:
    session, transport = make()
    session.open()
    assert transport.written == b""


def test_open_with_probe_verifies_the_link() -> None:
    session, transport = make(IDN)
    session.open(probe=True)
    assert transport.written == b"*IDN?\n"
    assert session.health.communication_ok is True


def test_a_failed_probe_leaves_nothing_open() -> None:
    """A partial connection failure must release everything it acquired."""
    session, transport = make()
    transport.fail_next_read(TransportError("silent instrument"), fault=False)
    with pytest.raises(TransportError):
        session.open(probe=True)
    assert session.is_connected is False
    assert transport.state is TransportState.CLOSED
    assert session.health.connected is False


def test_open_lets_a_driver_reject_the_wrong_instrument() -> None:
    session, _ = make(IDN)

    def expect_tektronix(identity: object) -> None:
        raise IdentityError("expected a TEKTRONIX scope")

    with pytest.raises(IdentityError):
        session.open(validate_identity=expect_tektronix)
    assert session.is_connected is False


def test_open_passes_the_parsed_identity_to_the_validator() -> None:
    session, _ = make(IDN)
    seen = []
    session.open(validate_identity=seen.append)
    assert seen[0].manufacturer == "KEYSIGHT"
    assert seen[0].model == "N6700C"
    assert session.is_connected is True


def test_validation_alone_still_queries_identity() -> None:
    session, transport = make(IDN)
    session.open(validate_identity=lambda identity: None)
    assert transport.written == b"*IDN?\n"


def test_a_failed_open_does_not_fall_back_to_anything() -> None:
    """A hardware connection that fails must fail, not quietly become a simulation."""
    session, transport = make()
    transport.fail_next_open(TransportError("no route to host"))
    with pytest.raises(TransportError):
        session.open()
    assert session.is_connected is False


# -- closing --------------------------------------------------------------


def test_close_marks_the_session_disconnected() -> None:
    session, _ = make()
    session.open()
    session.close()
    assert session.is_connected is False
    assert session.health.connected is False
    assert session.health.communication_ok is None


def test_close_is_idempotent() -> None:
    session, _ = make()
    session.open()
    session.close()
    session.close()
    assert session.is_connected is False


def test_close_clears_state_even_if_the_transport_fails_to_close() -> None:
    session, transport = make()
    session.open()

    def boom() -> None:
        raise TransportError("stuck")

    transport.close = boom  # type: ignore[method-assign]
    with pytest.raises(TransportError):
        session.close()
    assert session.health.connected is False


def test_operation_lock_is_usable_for_compound_sequences() -> None:
    session, transport = make(b"1.5\n")
    session.open()
    with session.operation_lock():  # type: ignore[attr-defined]
        assert session.client.query_float("MEAS?") == 1.5


# -- communication timeout ------------------------------------------------


def test_communication_timeout_defaults_to_deferring() -> None:
    session, _ = make()
    assert session.communication_timeout_s is None


def test_communication_timeout_is_applied_to_the_health_query() -> None:
    session, transport = make(IDN)
    session.set_communication_timeout(2.5)
    session.open()
    session.check_communication()
    assert transport.operations[-1].timeout_s == 2.5


def test_an_explicit_per_call_timeout_wins() -> None:
    session, transport = make(IDN)
    session.set_communication_timeout(2.5)
    session.open()
    session.check_communication(timeout_s=0.5)
    assert transport.operations[-1].timeout_s == 0.5


def test_communication_timeout_can_be_set_at_construction() -> None:
    transport = MockTransport()
    transport.feed(IDN)
    session = ScpiSession("default", ScpiClient(transport), communication_timeout_s=7.0)
    assert session.communication_timeout_s == 7.0


@pytest.mark.parametrize("timeout_s", [0, -1.0, float("inf"), float("nan")])
def test_communication_timeout_rejects_unbounded_values(timeout_s: float) -> None:
    session, _ = make()
    with pytest.raises(ConfigurationError):
        session.set_communication_timeout(timeout_s)


def test_communication_timeout_can_be_cleared() -> None:
    session, _ = make()
    session.set_communication_timeout(2.0)
    session.set_communication_timeout(None)
    assert session.communication_timeout_s is None


# -- trace context --------------------------------------------------------


def test_session_publishes_its_alias_and_generation_to_the_tracer() -> None:
    from scpi_driver_core.tracing import RecordingTraceObserver, Tracer

    transport = MockTransport()
    tracer = Tracer(RecordingTraceObserver())
    session = ScpiSession("psu1", ScpiClient(transport), tracer=tracer)
    session.open()
    assert tracer.context.session_alias == "psu1"
    assert tracer.context.session_generation == 1


def test_reconnecting_advances_the_traced_generation() -> None:
    """A trace spanning a reconnect must not read as one unbroken connection."""
    from scpi_driver_core.tracing import RecordingTraceObserver, Tracer

    transport = MockTransport()
    tracer = Tracer(RecordingTraceObserver())
    session = ScpiSession("psu1", ScpiClient(transport), tracer=tracer)
    session.open()
    session.close()
    session.open()
    assert tracer.context.session_generation == 2


def test_a_session_without_a_tracer_works_normally() -> None:
    session, _ = make()
    session.open()
    assert session.tracer is None
    assert session.is_connected is True
