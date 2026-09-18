from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ResponseParseError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.execution.retry import (
    NO_RETRY,
    RetryAttempt,
    RetryPolicy,
    run_with_retry,
)


class Recorder:
    def __init__(self) -> None:
        self.slept: list[float] = []
        self.attempts: list[RetryAttempt] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)

    def observe(self, attempt: RetryAttempt) -> None:
        self.attempts.append(attempt)


class FakeClock:
    """A monotonic clock that only advances when ``sleep`` is called.

    Lets a test assert on ``max_elapsed_s`` behavior without waiting in real
    time: elapsed time tracks exactly the delays ``run_with_retry`` asked to
    sleep for, the same relationship ``time.monotonic``/``time.sleep`` have.
    """

    def __init__(self) -> None:
        self.elapsed = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.elapsed

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.elapsed += seconds


# -- policy ---------------------------------------------------------------


def test_default_policy_makes_one_attempt() -> None:
    assert NO_RETRY.attempts == 1
    assert NO_RETRY.retries is False


def test_a_multi_attempt_policy_reports_that_it_retries() -> None:
    assert RetryPolicy(attempts=3).retries is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0},
        {"attempts": -1},
        {"initial_delay_s": -0.1},
        {"initial_delay_s": float("inf")},
        {"backoff": 0},
        {"backoff": -2.0},
        {"backoff": float("nan")},
        {"fast_attempts": -1},
        {"max_delay_s": 0},
        {"max_delay_s": -1.0},
        {"max_delay_s": float("inf")},
        {"max_elapsed_s": 0},
        {"max_elapsed_s": -1.0},
        {"max_elapsed_s": float("nan")},
    ],
)
def test_policy_rejects_invalid_values(kwargs: dict[str, float]) -> None:
    with pytest.raises(ConfigurationError):
        RetryPolicy(**kwargs)  # type: ignore[arg-type]


def test_first_attempt_is_never_delayed() -> None:
    assert RetryPolicy(attempts=3, initial_delay_s=1.0).delay_before(1) == 0.0


def test_backoff_compounds() -> None:
    policy = RetryPolicy(attempts=4, initial_delay_s=0.5, backoff=2.0)
    assert policy.delay_before(2) == pytest.approx(0.5)
    assert policy.delay_before(3) == pytest.approx(1.0)
    assert policy.delay_before(4) == pytest.approx(2.0)


def test_constant_backoff_keeps_the_delay() -> None:
    policy = RetryPolicy(attempts=4, initial_delay_s=0.25, backoff=1.0)
    assert [policy.delay_before(n) for n in (2, 3, 4)] == [0.25, 0.25, 0.25]


def test_fast_attempts_extends_the_flat_plateau() -> None:
    """fast_attempts=5 means exactly five flat retries before backoff compounds."""
    policy = RetryPolicy(attempts=8, initial_delay_s=0.5, backoff=2.0, fast_attempts=5)
    assert [policy.delay_before(n) for n in range(2, 8)] == [0.5, 0.5, 0.5, 0.5, 0.5, 1.0]


def test_fast_attempts_zero_and_one_are_equivalent() -> None:
    """The first retry is always flat regardless, so 0 and 1 both mean just that one."""
    without = RetryPolicy(attempts=4, initial_delay_s=0.5, backoff=2.0, fast_attempts=0)
    with_one = RetryPolicy(attempts=4, initial_delay_s=0.5, backoff=2.0, fast_attempts=1)
    assert [without.delay_before(n) for n in (2, 3, 4)] == [
        with_one.delay_before(n) for n in (2, 3, 4)
    ]


def test_max_delay_s_caps_growth() -> None:
    policy = RetryPolicy(
        attempts=10, initial_delay_s=0.5, backoff=2.0, fast_attempts=5, max_delay_s=10.0
    )
    assert [round(policy.delay_before(n), 3) for n in range(2, 12)] == [
        0.5,
        0.5,
        0.5,
        0.5,
        0.5,
        1.0,
        2.0,
        4.0,
        8.0,
        10.0,
    ]


# -- running --------------------------------------------------------------


def test_success_runs_once() -> None:
    calls = [0]

    def operation() -> str:
        calls[0] += 1
        return "ok"

    assert run_with_retry(operation) == "ok"
    assert calls[0] == 1


def test_default_policy_does_not_retry_a_failure() -> None:
    """One attempt is the default; retrying instrument traffic must be asked for."""
    calls = [0]

    def operation() -> str:
        calls[0] += 1
        raise TransportError("dead")

    with pytest.raises(TransportError):
        run_with_retry(operation)
    assert calls[0] == 1


def test_retries_until_success() -> None:
    recorder = Recorder()
    outcomes = [TransportError("a"), TransportTimeoutError("b"), None]

    def operation() -> str:
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return "ok"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(attempts=3, initial_delay_s=0.1, backoff=2.0),
        sleep=recorder.sleep,
        on_attempt=recorder.observe,
    )
    assert result == "ok"
    assert recorder.slept == [pytest.approx(0.1), pytest.approx(0.2)]


def test_final_exception_is_preserved_unwrapped() -> None:
    """The caller must see the real reason it gave up, not a wrapper."""
    final = TransportError("third failure")
    outcomes = [TransportError("first"), TransportError("second"), final]

    def operation() -> str:
        raise outcomes.pop(0)

    with pytest.raises(TransportError) as caught:
        run_with_retry(operation, policy=RetryPolicy(attempts=3), sleep=lambda _: None)
    assert caught.value is final


def test_attempts_are_reported_for_tracing() -> None:
    recorder = Recorder()
    outcomes: list[BaseException | None] = [TransportError("a"), None]

    def operation() -> str:
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return "ok"

    run_with_retry(
        operation,
        policy=RetryPolicy(attempts=3),
        sleep=recorder.sleep,
        on_attempt=recorder.observe,
    )
    assert [(a.number, a.total) for a in recorder.attempts] == [(1, 3), (2, 3)]
    assert isinstance(recorder.attempts[0].error, TransportError)
    assert recorder.attempts[1].error is None


def test_every_failed_attempt_is_reported() -> None:
    recorder = Recorder()

    def operation() -> str:
        raise TransportError("dead")

    with pytest.raises(TransportError):
        run_with_retry(
            operation,
            policy=RetryPolicy(attempts=3),
            sleep=recorder.sleep,
            on_attempt=recorder.observe,
        )
    assert len(recorder.attempts) == 3
    assert all(a.error is not None for a in recorder.attempts)


def test_unlisted_exceptions_are_not_retried() -> None:
    """A parse failure is not a transient fault; retrying it only wastes the delay."""
    calls = [0]

    def operation() -> str:
        calls[0] += 1
        raise ResponseParseError("not a float")

    with pytest.raises(ResponseParseError):
        run_with_retry(operation, policy=RetryPolicy(attempts=5), sleep=lambda _: None)
    assert calls[0] == 1


def test_retry_on_can_be_widened() -> None:
    calls = [0]

    def operation() -> str:
        calls[0] += 1
        if calls[0] < 2:
            raise ResponseParseError("flaky")
        return "ok"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(attempts=3),
        retry_on=(ResponseParseError,),
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert calls[0] == 2


def test_zero_delay_policy_does_not_sleep() -> None:
    recorder = Recorder()
    outcomes: list[BaseException | None] = [TransportError("a"), None]

    def operation() -> str:
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return "ok"

    run_with_retry(operation, policy=RetryPolicy(attempts=2), sleep=recorder.sleep)
    assert recorder.slept == []


def test_max_elapsed_s_stops_before_crossing_the_budget() -> None:
    """A deadline bounds wall-clock time, independently of the attempts count."""
    clock = FakeClock()
    calls = [0]

    def operation() -> str:
        calls[0] += 1
        raise TransportError("still slow")

    policy = RetryPolicy(attempts=100, initial_delay_s=0.5, backoff=1.0, max_elapsed_s=1.2)
    with pytest.raises(TransportError):
        run_with_retry(operation, policy=policy, sleep=clock.sleep, now=clock.now)

    # attempt 1 (no delay), attempt 2 (0.5s), attempt 3 (0.5s, elapsed -> 1.0s);
    # attempt 4 would need 0.5s more (elapsed 1.5s > 1.2s budget), so it never runs.
    assert calls[0] == 3
    assert clock.slept == [0.5, 0.5]


def test_max_elapsed_s_raises_the_last_real_error_not_a_timeout_wrapper() -> None:
    """Hitting the deadline doesn't invent a new exception type."""
    clock = FakeClock()
    final = TransportTimeoutError("TMO")
    outcomes = [TransportTimeoutError("a"), final]

    def operation() -> str:
        raise outcomes.pop(0) if outcomes else final

    policy = RetryPolicy(attempts=100, initial_delay_s=1.0, backoff=1.0, max_elapsed_s=1.0)
    with pytest.raises(TransportTimeoutError) as caught:
        run_with_retry(operation, policy=policy, sleep=clock.sleep, now=clock.now)
    assert caught.value is final


def test_without_max_elapsed_s_the_deadline_never_triggers() -> None:
    clock = FakeClock()
    calls = [0]
    outcomes: list[BaseException | None] = [TransportError("a"), TransportError("b"), None]

    def operation() -> str:
        calls[0] += 1
        outcome = outcomes.pop(0)
        if outcome is not None:
            raise outcome
        return "ok"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(attempts=3, initial_delay_s=10.0),
        sleep=clock.sleep,
        now=clock.now,
    )
    assert result == "ok"
    assert calls[0] == 3


# -- constant() -------------------------------------------------------------


def test_constant_builds_an_equivalent_policy() -> None:
    assert RetryPolicy.constant(100, 5.0) == RetryPolicy(
        attempts=100, initial_delay_s=5.0, backoff=1.0
    )


def test_constant_keeps_the_same_delay_every_attempt() -> None:
    policy = RetryPolicy.constant(attempts=5, delay_s=5.0)
    assert [policy.delay_before(n) for n in range(2, 6)] == [5.0, 5.0, 5.0, 5.0]


def test_constant_rejects_invalid_values() -> None:
    with pytest.raises(ConfigurationError):
        RetryPolicy.constant(0, 5.0)
    with pytest.raises(ConfigurationError):
        RetryPolicy.constant(3, -1.0)


# -- progressive() ------------------------------------------------------------


def test_progressive_builds_the_equivalent_policy() -> None:
    policy = RetryPolicy.progressive(50, 0.5, fast_attempts=5, max_delay_s=10.0, max_elapsed_s=60.0)
    assert policy == RetryPolicy(
        attempts=50,
        initial_delay_s=0.5,
        backoff=2.0,
        fast_attempts=5,
        max_delay_s=10.0,
        max_elapsed_s=60.0,
    )


def test_progressive_defaults_to_doubling_with_no_plateau_or_caps() -> None:
    policy = RetryPolicy.progressive(5, 1.0)
    assert policy.backoff == 2.0
    assert policy.fast_attempts == 0
    assert policy.max_delay_s is None
    assert policy.max_elapsed_s is None


def test_progressive_matches_the_fast_then_backoff_then_deadline_shape() -> None:
    """The exact scenario progressive() exists for: fast retries, then backoff, then give up."""
    clock = FakeClock()
    calls = [0]

    def operation() -> str:
        calls[0] += 1
        raise TransportError("device still busy")

    policy = RetryPolicy.progressive(
        attempts=1000, initial_delay_s=0.5, fast_attempts=5, max_delay_s=10.0, max_elapsed_s=20.0
    )
    with pytest.raises(TransportError):
        run_with_retry(operation, policy=policy, sleep=clock.sleep, now=clock.now)

    # 5 flat 0.5s retries, then 1.0, 2.0, 4.0, 8.0, 10.0(capped), 10.0... until the
    # 20s budget is crossed rather than running all 1000 configured attempts.
    assert clock.slept[:5] == [0.5, 0.5, 0.5, 0.5, 0.5]
    assert clock.slept[5:9] == [1.0, 2.0, 4.0, 8.0]
    assert all(s == 10.0 for s in clock.slept[9:])
    assert calls[0] < 1000
    assert clock.elapsed <= 20.0
