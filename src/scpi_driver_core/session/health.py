"""Communication health, tracked separately from transport state."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from scpi_driver_core.exceptions import ScpiDriverError

__all__ = ["SessionHealth"]


@dataclass
class SessionHealth:
    """Snapshot of connection/resource state and recent communication outcome."""

    connected: bool = False
    communication_ok: bool | None = None
    last_success_monotonic: float | None = None
    last_failure_monotonic: float | None = None
    last_error: ScpiDriverError | None = None

    def record_connected(self) -> None:
        self.connected = True
        self.communication_ok = None
        self.last_error = None

    def record_disconnected(self) -> None:
        """Mark resource closed without erasing the failure that caused it."""
        self.connected = False

    def record_success(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.communication_ok = True
        self.last_success_monotonic = clock()
        self.last_error = None

    def record_failure(
        self, error: ScpiDriverError, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.communication_ok = False
        self.last_failure_monotonic = clock()
        self.last_error = error

    def record_protocol_failure(
        self, error: ScpiDriverError, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Record an unusable reply while preserving that communication occurred."""
        self.last_failure_monotonic = clock()
        self.last_error = error
