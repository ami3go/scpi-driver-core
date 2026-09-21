"""Trace observers and the tracer that feeds them."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

from scpi_driver_core.tracing.events import ProtocolTraceEvent, TraceContext, TraceDirection
from scpi_driver_core.tracing.redaction import Redactor
from scpi_driver_core.transport.models import TransportDescriptor

__all__ = ["RecordingTraceObserver", "TraceObserver", "Tracer"]

logger = logging.getLogger(__name__)
_MAX_COMMAND_CONTEXT = 1024


@runtime_checkable
class TraceObserver(Protocol):
    def on_event(self, event: ProtocolTraceEvent) -> None: ...


class RecordingTraceObserver:
    def __init__(self, *, maximum_events: int | None = 10_000) -> None:
        if maximum_events is not None and maximum_events <= 0:
            raise ValueError("maximum_events must be positive or None")
        self._events: deque[ProtocolTraceEvent] = deque(maxlen=maximum_events)
        self._lock = threading.Lock()

    def on_event(self, event: ProtocolTraceEvent) -> None:
        with self._lock:
            self._events.append(event)

    @property
    def events(self) -> list[ProtocolTraceEvent]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class Tracer:
    """Build trace events, redact fail-closed, and report observer data loss."""

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
        self._dropped = 0
        self._commands: dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._observer is not None

    @property
    def context(self) -> TraceContext:
        with self._lock:
            return self._context

    @property
    def dropped_events(self) -> int:
        with self._lock:
            return self._dropped

    def set_context(self, context: TraceContext) -> None:
        with self._lock:
            self._context = context

    def emit(
        self,
        direction: TraceDirection,
        *,
        data: bytes = b"",
        operation_id: str | None = None,
        descriptor: TransportDescriptor | None = None,
        context: TraceContext | None = None,
        success: bool = True,
        duration_s: float | None = None,
        error: BaseException | None = None,
    ) -> ProtocolTraceEvent | None:
        observer = self._observer
        if observer is None:
            return None

        source_text = self._decode_source(data)
        response_command: str | None = None
        with self._lock:
            if direction is TraceDirection.TX and operation_id is not None and source_text is not None:
                self._commands[operation_id] = source_text
                while len(self._commands) > _MAX_COMMAND_CONTEXT:
                    self._commands.pop(next(iter(self._commands)))
            elif direction is TraceDirection.RX and operation_id is not None:
                response_command = self._commands.pop(operation_id, None)
            elif direction is TraceDirection.ERROR and operation_id is not None:
                # A failed transaction is complete from the tracer's point of view.
                self._commands.pop(operation_id, None)

        text, event_data, redacted = self._render(
            direction, data, command=response_command
        )
        with self._lock:
            self._sequence += 1
            event = ProtocolTraceEvent(
                sequence=self._sequence,
                direction=direction,
                timestamp_utc=datetime.now(timezone.utc),
                monotonic_s=self._clock(),
                success=success,
                duration_s=duration_s,
                context=context if context is not None else self._context,
                operation_id=operation_id,
                descriptor=descriptor,
                data=event_data,
                text=text,
                redacted=redacted,
                error_category=type(error).__name__ if error is not None else None,
                error_message=str(error) if error is not None else None,
            )

        try:
            observer.on_event(event)
        except Exception as exc:  # logging failure must not become instrument failure
            with self._lock:
                self._dropped += 1
                dropped = self._dropped
            if dropped == 1 or dropped % 1000 == 0:
                logger.warning("trace observer failed (%d dropped): %r", dropped, exc)
        return event

    def _decode_source(self, data: bytes) -> str | None:
        if not data:
            return None
        try:
            return data.decode(self._encoding)
        except UnicodeDecodeError:
            if self._redactor is None:
                return None
            return data.decode("latin-1")

    def _render(
        self,
        direction: TraceDirection,
        data: bytes,
        *,
        command: str | None,
    ) -> tuple[str | None, bytes, bool]:
        if not data:
            return None, data, False
        lossless_primary = True
        try:
            source = data.decode(self._encoding)
            redaction_encoding = self._encoding
        except UnicodeDecodeError:
            if self._redactor is None:
                return None, data, False
            # latin-1 is a one-to-one byte view, so pattern redaction can never
            # be bypassed merely by including a non-ASCII byte.
            source = data.decode("latin-1")
            redaction_encoding = "latin-1"
            lossless_primary = False

        if self._redactor is None:
            return source, data, False
        if direction in (TraceDirection.TX, TraceDirection.ERROR):
            rendered = self._redactor.redact_command(source)
        elif direction is TraceDirection.RX:
            rendered = self._redactor.redact_response(source, command=command)
        else:
            return (source if lossless_primary else None), data, False

        changed = rendered != source
        if not changed:
            return (source if lossless_primary else None), data, False
        redacted_data = rendered.encode(redaction_encoding, errors="replace")
        return (rendered if lossless_primary else None), redacted_data, True
