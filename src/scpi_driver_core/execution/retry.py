"""Retry policy for operations a caller has classified as safe to repeat."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal, TypeVar

from scpi_driver_core.exceptions import ConfigurationError, TransportError

__all__ = ["NO_RETRY", "RetryAttempt", "RetryPolicy", "run_with_retry"]

_T = TypeVar("_T")
RetryPhase = Literal["recover", "operation"]


@dataclass(frozen=True)
class RetryPolicy:
    """How many times to try, and how long to wait between tries.

    ``max_elapsed_s`` bounds whether another attempt may *start*. It cannot
    pre-empt an attempt already executing; each operation therefore still needs
    its own finite timeout.
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
        return self.attempts > 1

    def delay_before(self, attempt: int) -> float:
        """Seconds to wait before 1-based ``attempt`` without overflow."""
        if attempt <= 1:
            return 0.0
        plateau = max(self.fast_attempts - 1, 0)
        exponent = max(0, (attempt - 2) - plateau)
        try:
            delay = self.initial_delay_s * (self.backoff**exponent)
        except OverflowError:
            delay = math.inf
        if self.max_delay_s is not None:
            return min(delay, self.max_delay_s)
        return delay

    @classmethod
    def constant(cls, attempts: int, delay_s: float) -> RetryPolicy:
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
        return cls(
            attempts=attempts,
            initial_delay_s=initial_delay_s,
            backoff=backoff,
            fast_attempts=fast_attempts,
            max_delay_s=max_delay_s,
            max_elapsed_s=max_elapsed_s,
        )


NO_RETRY: Final = RetryPolicy()


@dataclass(frozen=True)
class RetryAttempt:
    """One attempt's outcome, including whether recovery or operation failed."""

    number: int
    total: int
    error: BaseException | None
    delay_s: float
    phase: RetryPhase = "operation"


def run_with_retry(
    operation: Callable[[], _T],
    *,
    policy: RetryPolicy = NO_RETRY,
    retry_on: tuple[type[BaseException], ...] = (TransportError,),
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    before_retry: Callable[[], None] | None = None,
    on_attempt: Callable[[RetryAttempt], None] | None = None,
) -> _T:
    """Run ``operation`` under a bounded retry/recovery policy.

    A retryable failure from ``before_retry`` consumes that attempt and leaves
    the remaining budget intact. Non-retryable recovery failures propagate
    immediately. This is essential while an instrument is rebooting: several
    reconnect attempts may legitimately fail before the device returns.
    """
    last_error: BaseException | None = None
    start = now()

    for number in range(1, policy.attempts + 1):
        delay = policy.delay_before(number)
        if not math.isfinite(delay):
            break
        if (
            number > 1
            and policy.max_elapsed_s is not None
            and (now() - start) + delay > policy.max_elapsed_s
        ):
            break
        if delay > 0:
            sleep(delay)

        phase: RetryPhase = "operation"
        try:
            if number > 1 and before_retry is not None:
                phase = "recover"
                before_retry()
                phase = "operation"
            result = operation()
        except retry_on as exc:
            last_error = exc
            if on_attempt is not None:
                on_attempt(
                    RetryAttempt(
                        number=number,
                        total=policy.attempts,
                        error=exc,
                        delay_s=delay,
                        phase=phase,
                    )
                )
            continue

        if on_attempt is not None:
            on_attempt(
                RetryAttempt(
                    number=number,
                    total=policy.attempts,
                    error=None,
                    delay_s=delay,
                    phase="operation",
                )
            )
        return result

    if last_error is None:  # defensive: first attempt normally establishes it
        raise RuntimeError("retry policy exhausted without running an attempt")
    raise last_error
