"""The protocol trace record.

One event describes one thing that happened on the wire, with enough context to
reconstruct a session afterwards: when it happened on two clocks, which session
and connection generation it belonged to, which operation it was part of, and
whether it worked.

Both clocks are recorded on purpose. The UTC timestamp is what correlates a
trace with a test log or an operator's notes; the monotonic one is what
measures durations, since it cannot jump when the system clock is adjusted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from scpi_driver_core.transport.models import TransportDescriptor

__all__ = ["ProtocolTraceEvent", "TraceContext", "TraceDirection"]


class TraceDirection(Enum):
    """What kind of thing the event records."""

    OPEN = "open"
    CLOSE = "close"
    TX = "tx"
    RX = "rx"
    ERROR = "error"
    FLUSH = "flush"


@dataclass(frozen=True)
class TraceContext:
    """Which session an event belongs to.

    The generation is included so a trace spanning a reconnect cannot be read
    as one unbroken connection.
    """

    session_alias: str | None = None
    session_generation: int | None = None


@dataclass(frozen=True)
class ProtocolTraceEvent:
    """One recorded protocol event."""

    sequence: int
    direction: TraceDirection
    timestamp_utc: datetime
    monotonic_s: float
    success: bool = True
    duration_s: float | None = None
    context: TraceContext = field(default_factory=TraceContext)
    operation_id: str | None = None
    descriptor: TransportDescriptor | None = None
    data: bytes = b""
    text: str | None = None
    """The payload decoded as text, when it decodes cleanly. ``None`` for
    binary, which is normal for waveform and block transfers."""
    redacted: bool = False
    """Whether a redactor altered this payload. When true, :attr:`data` holds
    the redacted bytes, not what was really on the wire."""
    error_category: str | None = None
    """The exception class name, so traces can be grouped without unpickling."""
    error_message: str | None = None
