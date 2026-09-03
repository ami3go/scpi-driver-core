"""Trace observers and the tracer that feeds them."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from scpi_driver_core.tracing.events import (
    ProtocolTraceEvent,
    TraceContext,
    TraceDirection,
)
from scpi_driver_core.tracing.redaction import Redactor
from scpi_driver_core.transport.models import TransportDescriptor

__all__ = ["RecordingTraceObserver", "TraceObserver", "Tracer"]


@runtime_checkable
class TraceObserver(Protocol):
    """Receives protocol trace events.

    Implementations must not raise: an observer that throws would turn a
    logging problem into an instrument failure. :class:`Tracer` enforces this
    by swallowing observer errors.
    """

    def on_event(self, event: ProtocolTraceEvent) -> None: ...


class RecordingTraceObserver:
    """Keeps events in memory, for tests and short-lived inspection.

    Args:
        maximum_events: how many to retain. The oldest are dropped beyond this,
            so a long run cannot exhaust memory. ``None`` retains everything,
            which is only appropriate for a bounded test.
    """

    def __init__(self, *, maximum_events: int | None = 10_000) -> None:
        self._maximum = maximum_events
        self._events: list[ProtocolTraceEvent] = []
        self._lock = threading.Lock()

    def on_event(self, event: ProtocolTraceEvent) -> None:
        with self._lock:
            self._events.append(event)
            if self._maximum is not None and len(self._events) > self._maximum:
                del self._events[: len(self._events) - self._maximum]

    @property
    def events(self) -> list[ProtocolTraceEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class Tracer:
    """Builds trace events and hands them to an observer.

    The tracer owns the sequence counter, so numbering is unbroken and totally
    ordered even when several threads are talking to the same instrument.

    Redaction is applied here rather than in a sink, so every sink sees the
    same already-redacted payload. When a redactor changes the text, the raw
    bytes are replaced with the redacted encoding: leaving the originals in
    place would defeat the redaction the moment a sink wrote them out.

    Args:
        observer: where events go. ``None`` disables tracing entirely, with no
            event construction cost.
        context: which session events belong to; replaceable as generations
            change.
        redactor: applied to decoded text before an event is emitted.
        encoding: used to attempt decoding payloads for the text field.
    """

    def __init__(
        self,
        observer: TraceObserver | None,
        *,
        context: TraceContext | None = None,
        redactor: Redactor | None = None,
        encoding: str = "ascii",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._observer = observer
        self._context = context if context is not None else TraceContext()
        self._redactor = redactor
        self._encoding = encoding
        self._clock = clock
        self._sequence = 0
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._observer is not None

    @property
    def context(self) -> TraceContext:
        with self._lock:
            return self._context

    def set_context(self, context: TraceContext) -> None:
        """Replace the session context, typically after a reconnect."""
        with self._lock:
            self._context = context

    def emit(
        self,
        direction: TraceDirection,
        *,
        data: bytes = b"",
        operation_id: str | None = None,
        descriptor: TransportDescriptor | None = None,
        success: bool = True,
        duration_s: float | None = None,
        error: BaseException | None = None,
    ) -> ProtocolTraceEvent | None:
        """Record one event. Returns it, or ``None`` when tracing is off."""
        observer = self._observer
        if observer is None:
            return None

        text, redacted = self._render(direction, data)
        if redacted and text is not None:
            data = text.encode(self._encoding, errors="replace")

        with self._lock:
            self._sequence += 1
            event = ProtocolTraceEvent(
                sequence=self._sequence,
                direction=direction,
                timestamp_utc=datetime.now(timezone.utc),
                monotonic_s=self._clock(),
                success=success,
                duration_s=duration_s,
                context=self._context,
                operation_id=operation_id,
                descriptor=descriptor,
                data=data,
                text=text,
                redacted=redacted,
                error_category=type(error).__name__ if error is not None else None,
                error_message=str(error) if error is not None else None,
            )

        # A misbehaving observer is a logging problem, not an instrument one.
        with suppress(Exception):
            observer.on_event(event)
        return event

    def _render(self, direction: TraceDirection, data: bytes) -> tuple[str | None, bool]:
        """Decode the payload if possible and redact it, reporting whether it changed."""
        if not data:
            return None, False
        try:
            text = data.decode(self._encoding)
        except UnicodeDecodeError:
            # Binary payloads have no text for a string redactor to match on.
            return None, False

        if self._redactor is None:
            return text, False

        if direction is TraceDirection.TX:
            redacted_text = self._redactor.redact_command(text)
        elif direction is TraceDirection.RX:
            redacted_text = self._redactor.redact_response(text)
        else:
            return text, False

        return redacted_text, redacted_text != text
