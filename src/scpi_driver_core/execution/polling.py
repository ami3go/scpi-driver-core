"""Bounded polling against a monotonic deadline.

Every wait in this package is finite. The clock and sleep function are
injectable so tests can drive a wait deterministically instead of really
sleeping, and so a caller can substitute an interruptible sleep.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

from scpi_driver_core.exceptions import ConfigurationError, OperationTimeoutError

__all__ = ["PollResult", "poll_until"]


@dataclass(frozen=True)
class PollResult:
    """How a successful poll went."""

    elapsed_s: float
    attempts: int


def poll_until(
    predicate: Callable[[], bool],
    *,
    timeout_s: float,
    interval_s: float = 0.1,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    description: str = "condition",
) -> PollResult:
    """Call ``predicate`` until it returns true or ``timeout_s`` elapses.

    The predicate is evaluated once before any sleeping, so a condition that is
    already satisfied costs nothing. Each sleep is trimmed to what remains of
    the deadline, so the call never overshoots its bound by up to a whole
    interval.

    Args:
        predicate: the condition, re-evaluated each round.
        timeout_s: total bound, measured on a monotonic clock so a system clock
            adjustment cannot extend or collapse it.
        interval_s: pause between evaluations.
        clock: monotonic time source; injectable for deterministic tests.
        sleep: how to pause; injectable for the same reason.
        description: named in the timeout message.

    Returns:
        How long the wait took and how many evaluations it needed.

    Raises:
        ConfigurationError: if the bounds are not finite and positive.
        OperationTimeoutError: if the deadline passes first. The message
            reports the elapsed time and the number of attempts.
    """
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
    if not math.isfinite(interval_s) or interval_s <= 0:
        raise ConfigurationError(f"interval_s must be finite and positive, got {interval_s!r}")

    started = clock()
    deadline = started + timeout_s
    attempts = 0

    while True:
        attempts += 1
        if predicate():
            return PollResult(elapsed_s=clock() - started, attempts=attempts)

        now = clock()
        remaining = deadline - now
        if remaining <= 0:
            raise OperationTimeoutError(
                f"{description} not met within {timeout_s}s "
                f"(elapsed {now - started:.3f}s, {attempts} attempts)"
            )
        sleep(min(interval_s, remaining))
