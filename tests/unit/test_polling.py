from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import ConfigurationError, OperationTimeoutError
from scpi_driver_core.execution.polling import poll_until


class FakeClock:
    """A clock that only advances when something sleeps on it."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def test_returns_immediately_when_already_true() -> None:
    clock = FakeClock()
    result = poll_until(lambda: True, timeout_s=5.0, clock=clock.time, sleep=clock.sleep)
    assert result.attempts == 1
    assert result.elapsed_s == 0.0
    assert clock.sleeps == []


def test_polls_until_the_condition_holds() -> None:
    clock = FakeClock()
    remaining = [False, False, True]

    def predicate() -> bool:
        return remaining.pop(0)

    result = poll_until(
        predicate, timeout_s=5.0, interval_s=0.5, clock=clock.time, sleep=clock.sleep
    )
    assert result.attempts == 3
    assert clock.sleeps == [0.5, 0.5]
    assert result.elapsed_s == pytest.approx(1.0)


def test_times_out_and_reports_the_detail() -> None:
    clock = FakeClock()
    with pytest.raises(OperationTimeoutError) as caught:
        poll_until(
            lambda: False,
            timeout_s=1.0,
            interval_s=0.25,
            clock=clock.time,
            sleep=clock.sleep,
            description="output settled",
        )
    message = str(caught.value)
    assert "output settled" in message
    assert "1.0s" in message
    assert "attempts" in message


def test_never_sleeps_past_the_deadline() -> None:
    """The last sleep is trimmed rather than overshooting by a whole interval."""
    clock = FakeClock()
    with pytest.raises(OperationTimeoutError):
        poll_until(
            lambda: False, timeout_s=1.0, interval_s=0.3, clock=clock.time, sleep=clock.sleep
        )
    assert sum(clock.sleeps) == pytest.approx(1.0)
    assert clock.sleeps[-1] == pytest.approx(0.1)


def test_uses_a_monotonic_deadline_not_wall_time() -> None:
    """A clock that jumps backwards must not extend the wait."""
    clock = FakeClock()
    calls = [0]

    def predicate() -> bool:
        calls[0] += 1
        return False

    with pytest.raises(OperationTimeoutError):
        poll_until(predicate, timeout_s=0.5, interval_s=0.25, clock=clock.time, sleep=clock.sleep)
    assert calls[0] == 3  # initial plus two intervals, then the deadline


def test_predicate_exceptions_propagate() -> None:
    def predicate() -> bool:
        raise ValueError("instrument said no")

    with pytest.raises(ValueError, match="instrument said no"):
        poll_until(predicate, timeout_s=1.0)


@pytest.mark.parametrize("timeout_s", [0, -1, float("inf"), float("nan")])
def test_rejects_an_unbounded_timeout(timeout_s: float) -> None:
    with pytest.raises(ConfigurationError, match="timeout_s"):
        poll_until(lambda: True, timeout_s=timeout_s)


@pytest.mark.parametrize("interval_s", [0, -1, float("inf")])
def test_rejects_an_invalid_interval(interval_s: float) -> None:
    with pytest.raises(ConfigurationError, match="interval_s"):
        poll_until(lambda: True, timeout_s=1.0, interval_s=interval_s)


@pytest.mark.parametrize("backoff", [0, -1, float("inf"), float("nan")])
def test_rejects_an_invalid_backoff(backoff: float) -> None:
    with pytest.raises(ConfigurationError, match="backoff"):
        poll_until(lambda: True, timeout_s=1.0, backoff=backoff)


@pytest.mark.parametrize("maximum_interval_s", [0, -1, float("inf"), float("nan")])
def test_rejects_an_invalid_interval_ceiling(maximum_interval_s: float) -> None:
    with pytest.raises(ConfigurationError, match="maximum_interval_s"):
        poll_until(lambda: True, timeout_s=1.0, maximum_interval_s=maximum_interval_s)


def test_a_backing_off_interval_still_respects_the_deadline() -> None:
    """Growth must never let a sleep overshoot the bound."""
    slept: list[float] = []
    now = [0.0]

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        now[0] += seconds

    with pytest.raises(OperationTimeoutError):
        poll_until(
            lambda: False,
            timeout_s=1.0,
            interval_s=0.5,
            backoff=10.0,
            clock=lambda: now[0],
            sleep=sleep,
        )
    assert slept == [0.5, 0.5]  # the second sleep is trimmed from 5.0
    assert now[0] == 1.0


def test_works_against_the_real_clock() -> None:
    result = poll_until(lambda: True, timeout_s=1.0, interval_s=0.01)
    assert result.attempts == 1
