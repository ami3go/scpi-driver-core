"""Retry policy for operations a caller has classified as safe to repeat.

The default is one attempt. Retrying instrument traffic is not a neutral
convenience: once bytes may have reached the device, repeating them can mean a
second output-enable, a second trigger, or a second calibration write. So
nothing here retries unless the caller asks for it, and
:class:`~scpi_driver_core.transport.models.ReplayPolicy` records that the
caller has judged the specific operation idempotent.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, TypeVar

from scpi_driver_core.exceptions import ConfigurationError, TransportError

__all__ = ["NO_RETRY", "RetryAttempt", "RetryPolicy", "run_with_retry"]

_T = TypeVar("_T")


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to try, and how long to wait between tries.

    Args:
        attempts: total attempts including the first. One, the default, means
            no retrying at all.
        initial_delay_s: pause before the second attempt, and the flat pause
            used throughout ``fast_attempts``.
        backoff: multiplier applied to the delay after each failure once past
            ``fast_attempts``. ``1.0`` keeps the delay constant.
        fast_attempts: how many retries beyond the first stay at the flat
            ``initial_delay_s`` before ``backoff`` starts compounding. ``0``,
            the default, means backoff compounding starts immediately after
            the first retry, as it always did before this field existed.
        max_delay_s: ceiling on any single wait, so an exponential ``backoff``
            cannot grow unbounded over many attempts. ``None`` leaves it
            uncapped.
        max_elapsed_s: total wall-clock budget for retrying, measured from the
            first attempt. Once the wait before the next attempt would cross
            this budget, :func:`run_with_retry` stops and raises rather than
            waiting for it — this bounds *time*, independently of ``attempts``
            bounding *count*. ``None`` leaves it unbounded.

    Raises:
        ConfigurationError: if any field is out of range.
    """

    attempts: int = 1
    initial_delay_s: float = 0.0
    backoff: float = 1.0
    fast_attempts: int = 0
    max_delay_s: float | None = None
    max_elapsed_s: float | None = None

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ConfigurationError(f"attempts must be at least 1, got {self.attempts}")
        if not math.isfinite(self.initial_delay_s) or self.initial_delay_s < 0:
            raise ConfigurationError(
                f"initial_delay_s must be finite and non-negative, got {self.initial_delay_s!r}"
            )
        if not math.isfinite(self.backoff) or self.backoff <= 0:
            raise ConfigurationError(f"backoff must be finite and positive, got {self.backoff!r}")
        if self.fast_attempts < 0:
            raise ConfigurationError(
                f"fast_attempts must be non-negative, got {self.fast_attempts}"
            )
        if self.max_delay_s is not None and (
            not math.isfinite(self.max_delay_s) or self.max_delay_s <= 0
        ):
            raise ConfigurationError(
                f"max_delay_s must be finite and positive, got {self.max_delay_s!r}"
            )
        if self.max_elapsed_s is not None and (
            not math.isfinite(self.max_elapsed_s) or self.max_elapsed_s <= 0
        ):
            raise ConfigurationError(
                f"max_elapsed_s must be finite and positive, got {self.max_elapsed_s!r}"
            )

    @property
    def retries(self) -> bool:
        """Whether this policy will ever make a second attempt."""
        return self.attempts > 1

    def delay_before(self, attempt: int) -> float:
        """Seconds to wait before ``attempt``, which is 1-based.

        The first attempt is never delayed, and the first retry is always at
        the flat ``initial_delay_s`` baseline (``backoff**0``) — that much is
        true even with ``fast_attempts=0``. ``fast_attempts`` extends that
        plateau: with ``fast_attempts=5``, the first *five* retries all wait
        ``initial_delay_s``, and only the sixth retry onward compounds by
        ``backoff``. ``max_delay_s`` (if set) caps the result.
        """
        if attempt <= 1:
            return 0.0
        plateau = max(self.fast_attempts - 1, 0)
        exponent = max(0, (attempt - 2) - plateau)
        delay = self.initial_delay_s * (self.backoff**exponent)
        if self.max_delay_s is not None:
            delay = min(delay, self.max_delay_s)
        return delay

    @classmethod
    def constant(cls, attempts: int, delay_s: float) -> RetryPolicy:
        """A policy that waits the same ``delay_s`` before every retry.

        Equivalent to ``RetryPolicy(attempts=attempts, initial_delay_s=delay_s,
        backoff=1.0)``, spelled out for the common case of a fixed pause
        rather than a backing-off one, e.g. a slow instrument that needs a
        flat multi-second wait before its reply is ready to retry.
        """
        return cls(attempts=attempts, initial_delay_s=delay_s, backoff=1.0)

    @classmethod
    def progressive(
        cls,
        attempts: int,
        initial_delay_s: float,
        backoff: float = 2.0,
        *,
        fast_attempts: int = 0,
        max_delay_s: float | None = None,
        max_elapsed_s: float | None = None,
    ) -> RetryPolicy:
        """A policy that starts with quick retries, then backs off.

        The common "retry fast a few times, then slow down, then give up"
        shape: e.g. ``RetryPolicy.progressive(50, 0.5, fast_attempts=5,
        max_delay_s=10.0, max_elapsed_s=60.0)`` retries every 0.5s for the
        first 5 retries, then doubles the wait each time up to a 10s
        ceiling, and gives up once a minute has passed since the first
        attempt — whichever bound, ``attempts`` or ``max_elapsed_s``, is hit
        first.
        """
        return cls(
            attempts=attempts,
            initial_delay_s=initial_delay_s,
            backoff=backoff,
            fast_attempts=fast_attempts,
            max_delay_s=max_delay_s,
            max_elapsed_s=max_elapsed_s,
        )


NO_RETRY: Final = RetryPolicy()
"""The default: a single attempt, no delay."""


@dataclass(frozen=True)
class RetryAttempt:
    """One attempt's outcome, reported to the observer for tracing."""

    number: int
    total: int
    error: BaseException | None
    delay_s: float


def run_with_retry(
    operation: Callable[[], _T],
    *,
    policy: RetryPolicy = NO_RETRY,
    retry_on: tuple[type[BaseException], ...] = (TransportError,),
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    on_attempt: Callable[[RetryAttempt], None] | None = None,
) -> _T:
    """Run ``operation``, retrying it according to ``policy``.

    Args:
        operation: the work to attempt. It must be safe to repeat; deciding
            that is the caller's responsibility, not this function's.
        policy: how many attempts and how long to back off.
        retry_on: which exceptions justify another attempt. Anything else
            propagates immediately, so a parse failure or a configuration
            mistake is not retried into a delay.
        sleep: how to pause between attempts; injectable for tests.
        now: monotonic clock used to enforce ``policy.max_elapsed_s``;
            injectable for tests.
        on_attempt: called after every attempt, successful or not, so tracing
            can record how many were needed.

    Returns:
        Whatever ``operation`` returned.

    Raises:
        BaseException: the exception from the final attempt, unchanged. Earlier
            failures are reported through ``on_attempt`` rather than being
            wrapped or chained, so the caller sees the real reason it gave up.
            This is also what's raised if ``policy.max_elapsed_s`` is crossed:
            the deadline stops further attempts, it doesn't invent a new error.
    """
    last_error: BaseException
    start = now()
    for number in range(1, policy.attempts + 1):
        delay = policy.delay_before(number)
        if (
            number > 1
            and policy.max_elapsed_s is not None
            and (now() - start) + delay > policy.max_elapsed_s
        ):
            break
        if delay > 0:
            sleep(delay)
        try:
            result = operation()
        except retry_on as exc:
            last_error = exc
            if on_attempt is not None:
                on_attempt(
                    RetryAttempt(number=number, total=policy.attempts, error=exc, delay_s=delay)
                )
            continue
        if on_attempt is not None:
            on_attempt(
                RetryAttempt(number=number, total=policy.attempts, error=None, delay_s=delay)
            )
        return result

    raise last_error
