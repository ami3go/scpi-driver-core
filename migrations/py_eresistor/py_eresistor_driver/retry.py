"""Retry, backoff, and circuit-breaker helpers."""
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from enum import Enum

from .models import ReconnectConfig


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout_s: float = 30.0
    half_open_max_calls: int = 1

    def __post_init__(self) -> None:
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at: float | None = None
        self.half_open_calls = 0

    def allow_call(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.opened_at is not None and time.monotonic() - self.opened_at >= self.recovery_timeout_s:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        if self.state == CircuitState.HALF_OPEN:
            if self.half_open_calls < self.half_open_max_calls:
                self.half_open_calls += 1
                return True
            return False
        return False

    def record_success(self) -> None:
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at = None
        self.half_open_calls = 0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold or self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()


def backoff_delays(config: ReconnectConfig):
    attempt = 0
    delay = config.backoff_base_s
    while config.max_attempts is None or attempt < config.max_attempts:
        actual = min(delay, config.backoff_max_s)
        if config.jitter and actual > 0:
            actual *= random.uniform(0.75, 1.25)
        yield max(0.0, actual)
        delay *= config.backoff_multiplier
        attempt += 1
