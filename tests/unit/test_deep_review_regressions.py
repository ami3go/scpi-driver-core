from __future__ import annotations

import copy
import dataclasses
import pickle
import threading
from pathlib import Path

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    OperationTimeoutError,
    SafetyGuardError,
    ScpiTimeoutError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.execution.guards import ConfirmationGuard
from scpi_driver_core.execution.retry import RetryAttempt, RetryPolicy, run_with_retry
from scpi_driver_core.tracing import (
    JsonlTraceSink,
    PatternRedactor,
    RecordingTraceObserver,
    TraceDirection,
    Tracer,
)
from scpi_driver_core.transport import MockTransport, TransportDescriptor, TransportState


def test_retryable_recovery_failure_consumes_attempt_then_recovers() -> None:
    operation_calls = 0
    recovery_calls = 0
    observed: list[RetryAttempt] = []

    def operation() -> str:
        nonlocal operation_calls
        operation_calls += 1
        if operation_calls == 1:
            raise TransportError("instrument rebooting")
        return "ok"

    def recover() -> None:
        nonlocal recovery_calls
        recovery_calls += 1
        if recovery_calls == 1:
            raise TransportError("connection refused")

    assert (
        run_with_retry(
            operation,
            policy=RetryPolicy(attempts=3),
            before_retry=recover,
            on_attempt=observed.append,
        )
        == "ok"
    )
    assert operation_calls == 2
    assert recovery_calls == 2
    assert [attempt.phase for attempt in observed] == ["operation", "recover", "operation"]
    assert [attempt.number for attempt in observed] == [1, 2, 3]


def test_nonretryable_recovery_failure_propagates_immediately() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise TransportError("retry me")

    def recover() -> None:
        raise ConfigurationError("wrong instrument configuration")

    with pytest.raises(ConfigurationError, match="wrong instrument"):
        run_with_retry(operation, policy=RetryPolicy(attempts=5), before_retry=recover)
    assert calls == 1


def test_retry_backoff_cannot_overflow_when_capped() -> None:
    policy = RetryPolicy(
        attempts=20_000,
        initial_delay_s=0.1,
        backoff=2.0,
        max_delay_s=5.0,
    )
    assert policy.delay_before(10_000) == 5.0


def test_common_timeout_base_catches_transport_and_operation_timeouts() -> None:
    errors = [TransportTimeoutError("io"), OperationTimeoutError("operation")]
    assert all(isinstance(error, ScpiTimeoutError) for error in errors)
    assert isinstance(errors[0], TransportError)


def test_guard_scoped_enablement_is_thread_local() -> None:
    guard = ConfirmationGuard("CALIBRATE")
    entered = threading.Event()
    release = threading.Event()
    worker_error: list[BaseException] = []

    def worker() -> None:
        try:
            with guard.enabled("CALIBRATE"):
                assert guard.is_enabled
                entered.set()
                release.wait(timeout=2)
        except BaseException as exc:  # pragma: no cover - asserted below
            worker_error.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=1)
    assert guard.is_enabled is False
    with pytest.raises(SafetyGuardError):
        guard.require_enabled()
    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert worker_error == []


def test_guard_disable_revokes_open_scoped_window_without_blocking() -> None:
    guard = ConfirmationGuard("CALIBRATE")
    entered = threading.Event()
    revoked = threading.Event()
    result: list[bool] = []

    def worker() -> None:
        with guard.enabled("CALIBRATE"):
            entered.set()
            revoked.wait(timeout=2)
            try:
                guard.require_enabled()
            except SafetyGuardError:
                result.append(True)
            else:  # pragma: no cover - safety regression
                result.append(False)

    thread = threading.Thread(target=worker)
    thread.start()
    assert entered.wait(timeout=1)
    guard.disable()
    revoked.set()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert result == [True]


def test_descriptor_is_pickle_and_deepcopy_safe() -> None:
    descriptor = TransportDescriptor("tcp", "127.0.0.1:5025", {"role": "psu"})
    assert pickle.loads(pickle.dumps(descriptor)) == descriptor
    assert copy.deepcopy(descriptor) == descriptor
    rendered = dataclasses.asdict(descriptor)
    assert dict(rendered["metadata"]) == {"role": "psu"}
    with pytest.raises(TypeError):
        descriptor.metadata["role"] = "dmm"  # type: ignore[index]


def test_transport_context_manager_closes_after_exception() -> None:
    transport = MockTransport()
    with pytest.raises(RuntimeError), transport:
        assert transport.state is TransportState.OPEN
        raise RuntimeError("boom")
    assert transport.state is TransportState.CLOSED


def test_undecodable_secret_is_still_redacted() -> None:
    observer = RecordingTraceObserver()
    redactor = PatternRedactor([r'SYST:SEC:CODE "?([^"\s]+)'])
    tracer = Tracer(observer, redactor=redactor)
    tracer.emit(TraceDirection.TX, data=b'SYST:SEC:CODE "hunter2\xb5"\n')
    event = observer.events[-1]
    assert event.redacted is True
    assert b"hunter2" not in event.data


def test_sensitive_query_redacts_entire_response_using_command_context() -> None:
    observer = RecordingTraceObserver()
    redactor = PatternRedactor([], sensitive_queries=[r"^SYST:SEC:CODE\?"])
    tracer = Tracer(observer, redactor=redactor)
    tracer.emit(TraceDirection.TX, data=b"SYST:SEC:CODE?\n", operation_id="op-secret")
    tracer.emit(TraceDirection.RX, data=b"hunter2\n", operation_id="op-secret")
    event = observer.events[-1]
    assert event.redacted is True
    assert b"hunter2" not in event.data
    assert event.data == b"***"


def test_trace_observer_failure_is_counted_not_silent(caplog: pytest.LogCaptureFixture) -> None:
    class BrokenObserver:
        def on_event(self, event: object) -> None:
            del event
            raise OSError("disk full")

    tracer = Tracer(BrokenObserver())
    tracer.emit(TraceDirection.TX, data=b"*IDN?\n")
    assert tracer.dropped_events == 1
    assert "trace observer failed" in caplog.text


@pytest.mark.parametrize("maximum_payload_bytes", [0, -1])
def test_jsonl_rejects_nonpositive_payload_limit(maximum_payload_bytes: int) -> None:
    with pytest.raises(ConfigurationError):
        JsonlTraceSink(Path("unused.jsonl"), maximum_payload_bytes=maximum_payload_bytes)
