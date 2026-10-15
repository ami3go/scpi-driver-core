"""Internal, single-operation monotonic I/O budget.

The deadline is intentionally independent of transport type, backend retries
and vendor command semantics. A backend may block for the requested remaining
duration, but partial progress never renews that duration.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from scpi_driver_core.exceptions import ConfigurationError, TransportTimeoutError

if TYPE_CHECKING:
    from scpi_driver_core.transport.base import Transport


class Deadline:
    """Private monotonic budget used by multi-stage transport operations."""

    def __init__(self, timeout_s: float, *, clock: Callable[[], float] | None = None) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
        self._clock = time.monotonic if clock is None else clock
        self._ends_at = self._clock() + timeout_s

    def remaining(self) -> float:
        remaining_s = self._ends_at - self._clock()
        if remaining_s <= 0:
            raise TransportTimeoutError("SCPI operation deadline exceeded")
        return remaining_s


def operation_deadline(transport: Transport, timeout_s: float | None) -> Deadline | None:
    """Resolve a total budget without changing legacy custom transports.

    Core backends and supported wrappers expose the configured default timeout.
    Third-party transports that do not expose this optional property continue
    to accept explicit timeouts; callers should pass a timeout for multi-step
    operations if they cannot supply a default_timeout_s property.
    """
    effective = timeout_s
    if effective is None:
        # Transparent wrappers (e.g. traced transports) preserve the inner
        # transport's configured default without changing the Transport protocol.
        candidate: object = transport
        for _ in range(8):
            effective = getattr(candidate, "default_timeout_s", None)
            if effective is not None:
                break
            nested = getattr(candidate, "inner", None)
            if nested is None or nested is candidate:
                return None
            candidate = nested
        if effective is None:
            return None
    return Deadline(effective)
