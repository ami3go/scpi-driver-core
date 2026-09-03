from __future__ import annotations

import json
from datetime import timezone
from io import StringIO
from pathlib import Path

import pytest

from scpi_driver_core.exceptions import TransportError
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.tracing import (
    SCHEMA_VERSION,
    InstrumentedTransport,
    JsonlTraceSink,
    PatternRedactor,
    RecordingTraceObserver,
    TraceContext,
    TraceDirection,
    Tracer,
)
from scpi_driver_core.transport import (
    FlushDirection,
    MockTransport,
    ReadMode,
    ReadRequest,
    Transport,
    TransportDescriptor,
)

LINE = ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")


def traced(
    *replies: bytes, **tracer_kwargs: object
) -> tuple[InstrumentedTransport, MockTransport, RecordingTraceObserver]:
    inner = MockTransport()
    for reply in replies:
        inner.feed(reply)
    observer = RecordingTraceObserver()
    tracer = Tracer(observer, **tracer_kwargs)  # type: ignore[arg-type]
    return InstrumentedTransport(inner, tracer), inner, observer


# -- the observer ---------------------------------------------------------


def test_recording_observer_keeps_order() -> None:
    transport, _, observer = traced(b"1.5\n")
    transport.open()
    transport.write(b"MEAS?\n")
    transport.read(LINE)
    transport.close()
    assert [event.direction for event in observer.events] == [
        TraceDirection.OPEN,
        TraceDirection.TX,
        TraceDirection.RX,
        TraceDirection.CLOSE,
    ]


def test_recording_observer_is_bounded() -> None:
    """A long run must not exhaust memory through the trace buffer."""
    observer = RecordingTraceObserver(maximum_events=3)
    tracer = Tracer(observer)
    for _ in range(10):
        tracer.emit(TraceDirection.TX, data=b"x")
    assert len(observer.events) == 3
    assert [event.sequence for event in observer.events] == [8, 9, 10]


def test_recording_observer_can_be_cleared() -> None:
    observer = RecordingTraceObserver()
    Tracer(observer).emit(TraceDirection.TX, data=b"x")
    observer.clear()
    assert observer.events == []


def test_sequence_numbers_are_unbroken() -> None:
    transport, _, observer = traced(b"a\n", b"b\n")
    transport.open()
    for _ in range(2):
        transport.write(b"Q\n")
        transport.read(LINE)
    assert [event.sequence for event in observer.events] == [1, 2, 3, 4, 5]


def test_tracing_is_off_without_an_observer() -> None:
    tracer = Tracer(None)
    assert tracer.enabled is False
    assert tracer.emit(TraceDirection.TX, data=b"x") is None


def test_a_broken_observer_does_not_break_io() -> None:
    """A logging fault must never become an instrument failure."""

    class Broken:
        def on_event(self, event: object) -> None:
            raise RuntimeError("sink is on fire")

    inner = MockTransport()
    inner.feed(b"1.5\n")
    transport = InstrumentedTransport(inner, Tracer(Broken()))
    transport.open()
    transport.write(b"MEAS?\n")
    assert transport.read(LINE) == b"1.5"


# -- event content --------------------------------------------------------


def test_events_carry_both_clocks() -> None:
    transport, _, observer = traced()
    transport.open()
    event = observer.events[0]
    assert event.timestamp_utc.tzinfo == timezone.utc
    assert isinstance(event.monotonic_s, float)
    assert event.duration_s is not None


def test_events_carry_the_transport_descriptor() -> None:
    transport, inner, observer = traced()
    transport.open()
    assert observer.events[0].descriptor == inner.descriptor


def test_events_carry_session_alias_and_generation() -> None:
    transport, _, observer = traced(
        context=TraceContext(session_alias="psu1", session_generation=3)
    )
    transport.open()
    event = observer.events[0]
    assert event.context.session_alias == "psu1"
    assert event.context.session_generation == 3


def test_context_can_be_replaced_after_a_reconnect() -> None:
    transport, _, observer = traced(context=TraceContext("psu1", 1))
    transport.open()
    transport.tracer.set_context(TraceContext("psu1", 2))
    transport.close()
    assert [event.context.session_generation for event in observer.events] == [1, 2]


def test_operation_ids_correlate_a_transaction() -> None:
    transport, _, observer = traced(b"1.5\n")
    transport.open()
    transport.transact(b"MEAS?\n", LINE, operation_id="op-9")
    io_events = [
        e for e in observer.events if e.direction in (TraceDirection.TX, TraceDirection.RX)
    ]
    assert [e.operation_id for e in io_events] == ["op-9", "op-9"]


def test_text_is_decoded_when_valid() -> None:
    transport, _, observer = traced()
    transport.open()
    transport.write(b"*IDN?\n")
    assert observer.events[-1].text == "*IDN?\n"
    assert observer.events[-1].data == b"*IDN?\n"


def test_binary_payloads_have_no_text_but_keep_their_bytes() -> None:
    payload = bytes(range(256))
    transport, inner, observer = traced()
    transport.open()
    inner.feed(payload)
    transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=len(payload)))
    event = observer.events[-1]
    assert event.text is None
    assert event.data == payload


# -- failures -------------------------------------------------------------


def test_a_failed_read_is_traced_then_re_raised() -> None:
    transport, inner, observer = traced()
    transport.open()
    inner.fail_next_read(TransportError("cable pulled"), fault=False)
    with pytest.raises(TransportError):
        transport.read(LINE)
    event = observer.events[-1]
    assert event.success is False
    assert event.direction is TraceDirection.RX
    assert event.error_category == "TransportError"
    assert "cable pulled" in (event.error_message or "")


def test_a_failed_open_is_traced() -> None:
    transport, inner, observer = traced()
    inner.fail_next_open(TransportError("no route"))
    with pytest.raises(TransportError):
        transport.open()
    assert observer.events[-1].direction is TraceDirection.OPEN
    assert observer.events[-1].success is False


def test_a_failed_write_is_traced_with_its_payload() -> None:
    transport, inner, observer = traced()
    transport.open()
    inner.fail_next_write(TransportError("dead"), fault=False)
    with pytest.raises(TransportError):
        transport.write(b"VOLT 1\n")
    assert observer.events[-1].data == b"VOLT 1\n"
    assert observer.events[-1].success is False


def test_a_failed_close_is_traced() -> None:
    transport, inner, observer = traced()
    transport.open()

    def boom() -> None:
        raise TransportError("stuck")

    inner.close = boom  # type: ignore[method-assign]
    with pytest.raises(TransportError):
        transport.close()
    assert observer.events[-1].direction is TraceDirection.CLOSE
    assert observer.events[-1].success is False


def test_a_failed_flush_is_traced() -> None:
    transport, inner, observer = traced()
    transport.open()

    def boom(direction: FlushDirection) -> None:
        raise TransportError("stuck")

    inner.flush = boom  # type: ignore[method-assign]
    with pytest.raises(TransportError):
        transport.flush(FlushDirection.BOTH)
    assert observer.events[-1].success is False


def test_a_failed_transaction_traces_both_halves() -> None:
    transport, inner, observer = traced()
    transport.open()
    inner.fail_next_read(TransportError("silent"), fault=False)
    with pytest.raises(TransportError):
        transport.transact(b"MEAS?\n", LINE, operation_id="op-1")
    directions = [e.direction for e in observer.events[1:]]
    assert directions == [TraceDirection.TX, TraceDirection.RX]
    assert observer.events[-1].success is False


def test_flush_is_traced() -> None:
    transport, _, observer = traced()
    transport.open()
    transport.flush(FlushDirection.BOTH)
    assert observer.events[-1].direction is TraceDirection.FLUSH


# -- transparency ---------------------------------------------------------


def test_the_wrapper_satisfies_the_transport_protocol() -> None:
    transport, _, _ = traced()
    assert isinstance(transport, Transport)


def test_the_wrapper_changes_no_bytes() -> None:
    payload = b"\x00\xff  \t trailing \x00"
    transport, inner, _ = traced()
    transport.open()
    inner.feed(payload)
    assert transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=len(payload))) == payload
    transport.write(payload)
    assert inner.written == payload


def test_the_wrapper_plugs_under_the_client() -> None:
    transport, _, observer = traced(b"1.5\n")
    transport.open()
    assert ScpiClient(transport).query_float("MEAS?") == 1.5
    assert any(event.direction is TraceDirection.TX for event in observer.events)


def test_state_queries_are_not_traced() -> None:
    """Reading state is not wire activity and would only add noise."""
    transport, _, observer = traced()
    transport.open()
    before = len(observer.events)
    assert transport.is_open is True
    assert transport.state is not None
    assert transport.descriptor is not None
    assert len(observer.events) == before


def test_inner_transport_is_reachable() -> None:
    transport, inner, _ = traced()
    assert transport.inner is inner


# -- redaction ------------------------------------------------------------


def test_redaction_replaces_a_secret_in_a_command() -> None:
    redactor = PatternRedactor([r"CAL:SEC:CODE (\S+)"])
    transport, _, observer = traced(redactor=redactor)
    transport.open()
    transport.write(b"CAL:SEC:CODE hunter2\n")
    event = observer.events[-1]
    assert "hunter2" not in (event.text or "")
    assert event.text == "CAL:SEC:CODE ***\n"
    assert event.redacted is True


def test_redaction_also_rewrites_the_raw_bytes() -> None:
    """Redacting only the text would leak the secret the moment a sink wrote bytes."""
    redactor = PatternRedactor([r"CAL:SEC:CODE (\S+)"])
    transport, _, observer = traced(redactor=redactor)
    transport.open()
    transport.write(b"CAL:SEC:CODE hunter2\n")
    assert b"hunter2" not in observer.events[-1].data


def test_redaction_leaves_unmatched_traffic_alone() -> None:
    redactor = PatternRedactor([r"CAL:SEC:CODE (\S+)"])
    transport, _, observer = traced(redactor=redactor)
    transport.open()
    transport.write(b"MEAS:VOLT?\n")
    assert observer.events[-1].text == "MEAS:VOLT?\n"
    assert observer.events[-1].redacted is False


def test_redaction_applies_to_responses() -> None:
    redactor = PatternRedactor([r"SECRET=(\w+)"])
    transport, _, observer = traced(b"SECRET=abc123\n", redactor=redactor)
    transport.open()
    transport.read(LINE)
    assert "abc123" not in (observer.events[-1].text or "")


def test_pattern_without_a_group_replaces_the_whole_match() -> None:
    redactor = PatternRedactor([r"hunter2"])
    assert redactor.redact_command("CODE hunter2") == "CODE ***"


def test_response_patterns_can_differ_from_command_patterns() -> None:
    redactor = PatternRedactor([r"OUT=(\w+)"], response_patterns=[r"IN=(\w+)"])
    assert redactor.redact_command("OUT=x IN=y") == "OUT=*** IN=y"
    assert redactor.redact_response("OUT=x IN=y") == "OUT=x IN=***"


def test_placeholder_is_configurable() -> None:
    redactor = PatternRedactor([r"(secret)"], placeholder="[REDACTED]")
    assert redactor.redact_command("a secret b") == "a [REDACTED] b"


# -- the JSONL sink -------------------------------------------------------


def read_lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_jsonl_writes_one_object_per_event(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    inner = MockTransport()
    inner.feed(b"1.5\n")
    with JsonlTraceSink(path) as sink:
        transport = InstrumentedTransport(inner, Tracer(sink))
        transport.open()
        transport.write(b"MEAS?\n")
        transport.read(LINE)
        transport.close()
    records = read_lines(path)
    assert [record["direction"] for record in records] == ["open", "tx", "rx", "close"]


def test_jsonl_records_carry_the_schema_version(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path) as sink:
        Tracer(sink).emit(TraceDirection.TX, data=b"x")
    assert read_lines(path)[0]["schema_version"] == SCHEMA_VERSION


def test_jsonl_is_append_only(tmp_path: Path) -> None:
    """A second run must extend the audit, never truncate it."""
    path = tmp_path / "trace.jsonl"
    for _ in range(2):
        with JsonlTraceSink(path) as sink:
            Tracer(sink).emit(TraceDirection.TX, data=b"x")
    assert len(read_lines(path)) == 2


def test_jsonl_encodes_binary_deterministically(tmp_path: Path) -> None:
    import base64

    payload = bytes(range(256))
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path, maximum_payload_bytes=1024) as sink:
        Tracer(sink).emit(TraceDirection.RX, data=payload)
    record = read_lines(path)[0]
    assert base64.b64decode(str(record["payload_base64"])) == payload
    assert record["payload_length"] == 256


def test_jsonl_truncates_a_large_payload_but_records_its_size(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path, maximum_payload_bytes=16) as sink:
        Tracer(sink).emit(TraceDirection.RX, data=b"x" * 5000)
    record = read_lines(path)[0]
    assert record["payload_truncated"] is True
    assert record["payload_length"] == 5000


def test_jsonl_can_omit_payloads_entirely(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path, include_payloads=False) as sink:
        Tracer(sink).emit(TraceDirection.TX, data=b"CAL:SEC:CODE hunter2")
    record = read_lines(path)[0]
    assert "payload_base64" not in record
    assert "text" not in record


def test_jsonl_records_correlation_fields(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path) as sink:
        tracer = Tracer(sink, context=TraceContext("psu1", 2))
        tracer.emit(TraceDirection.TX, data=b"x", operation_id="op-4")
    record = read_lines(path)[0]
    assert record["session_alias"] == "psu1"
    assert record["session_generation"] == 2
    assert record["operation_id"] == "op-4"


def test_jsonl_records_failures(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path) as sink:
        Tracer(sink).emit(TraceDirection.RX, success=False, error=TransportError("cable pulled"))
    record = read_lines(path)[0]
    assert record["success"] is False
    assert record["error_category"] == "TransportError"
    assert "cable pulled" in str(record["error_message"])


def test_jsonl_marks_redacted_records(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path) as sink:
        tracer = Tracer(sink, redactor=PatternRedactor([r"CODE (\S+)"]))
        tracer.emit(TraceDirection.TX, data=b"CODE hunter2")
    record = read_lines(path)[0]
    assert record["redacted"] is True
    assert "hunter2" not in json.dumps(record)


def test_jsonl_records_the_transport_descriptor(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    inner = MockTransport()
    with JsonlTraceSink(path) as sink:
        InstrumentedTransport(inner, Tracer(sink)).open()
    transport = read_lines(path)[0]["transport"]
    assert isinstance(transport, dict)
    assert transport["kind"] == "mock"


def test_jsonl_accepts_a_borrowed_stream_and_leaves_it_open() -> None:
    stream = StringIO()
    sink = JsonlTraceSink(stream)
    Tracer(sink).emit(TraceDirection.TX, data=b"x")
    sink.close()
    assert stream.closed is False
    assert json.loads(stream.getvalue().splitlines()[0])["direction"] == "tx"


def test_jsonl_close_is_idempotent(tmp_path: Path) -> None:
    sink = JsonlTraceSink(tmp_path / "trace.jsonl")
    sink.close()
    sink.close()


def test_jsonl_ignores_events_after_close(tmp_path: Path) -> None:
    """Shutdown ordering must not turn into an instrument failure."""
    path = tmp_path / "trace.jsonl"
    sink = JsonlTraceSink(path)
    sink.close()
    Tracer(sink).emit(TraceDirection.TX, data=b"x")
    assert read_lines(path) == []


def test_jsonl_flush_is_safe_before_and_after_close(tmp_path: Path) -> None:
    sink = JsonlTraceSink(tmp_path / "trace.jsonl")
    sink.flush()
    sink.close()
    sink.flush()


def test_jsonl_without_per_event_flush_still_writes_on_close(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    with JsonlTraceSink(path, flush_each_event=False) as sink:
        Tracer(sink).emit(TraceDirection.TX, data=b"x")
    assert len(read_lines(path)) == 1


def test_jsonl_records_descriptor_metadata(tmp_path: Path) -> None:
    path = tmp_path / "trace.jsonl"
    descriptor = TransportDescriptor(
        kind="visa", address="GPIB0::22::INSTR", metadata={"visa_library": "@py"}
    )
    inner = MockTransport(descriptor=descriptor)
    with JsonlTraceSink(path) as sink:
        InstrumentedTransport(inner, Tracer(sink)).open()
    transport = read_lines(path)[0]["transport"]
    assert isinstance(transport, dict)
    assert transport["metadata"] == {"visa_library": "@py"}


def test_redaction_applies_only_to_commands_and_responses() -> None:
    """Open, close and flush payloads are neither, so a redactor leaves them alone."""
    observer = RecordingTraceObserver()
    tracer = Tracer(observer, redactor=PatternRedactor([r"(secret)"]))
    tracer.emit(TraceDirection.OPEN, data=b"secret")
    event = observer.events[-1]
    assert event.text == "secret"
    assert event.redacted is False
