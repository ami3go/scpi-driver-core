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
        initial_delay_s: pause before the second attempt.
        backoff: multiplier applied to the delay after each failure. ``1.0``
            keeps the delay constant.

    Raises:
        ConfigurationError: if any field is out of range.
    """

    attempts: int = 1
    initial_delay_s: float = 0.0
    backoff: float = 1.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ConfigurationError(f"attempts must be at least 1, got {self.attempts}")
        if not math.isfinite(self.initial_delay_s) or self.initial_delay_s < 0:
            raise ConfigurationError(
                f"initial_delay_s must be finite and non-negative, got {self.initial_delay_s!r}"
            )
        if not math.isfinite(self.backoff) or self.backoff <= 0:
            raise ConfigurationError(f"backoff must be finite and positive, got {self.backoff!r}")

    @property
    def retries(self) -> bool:
        """Whether this policy will ever make a second attempt."""
        return self.attempts > 1

    def delay_before(self, attempt: int) -> float:
        """Seconds to wait before ``attempt``, which is 1-based.

        The first attempt is never delayed.
        """
        if attempt <= 1:
            return 0.0
        return self.initial_delay_s * (self.backoff ** (attempt - 2))


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
        on_attempt: called after every attempt, successful or not, so tracing
            can record how many were needed.

    Returns:
        Whatever ``operation`` returned.

    Raises:
        BaseException: the exception from the final attempt, unchanged. Earlier
            failures are reported through ``on_attempt`` rather than being
            wrapped or chained, so the caller sees the real reason it gave up.
    """
    last_error: BaseException
    for number in range(1, policy.attempts + 1):
        delay = policy.delay_before(number)
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
