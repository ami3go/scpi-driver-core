"""A transport wrapper that traces everything passing through it."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

from scpi_driver_core.tracing.events import TraceContext, TraceDirection
from scpi_driver_core.tracing.observer import Tracer
from scpi_driver_core.transport.base import Transport
from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)

__all__ = ["InstrumentedTransport"]

_CAPABILITY_NAMES = frozenset({"device_clear", "read_status_byte", "assert_trigger", "go_to_local"})


class InstrumentedTransport:
    """Trace a transport without changing its protocol behavior."""

    def __init__(
        self,
        inner: Transport,
        tracer: Tracer,
        *,
        context: TraceContext | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._tracer = tracer
        # ``None`` deliberately means "use the tracer's current context". A
        # session calls set_context() to pin a transport-local context when one
        # tracer is shared by several instruments. This keeps legacy
        # single-session tracer-context use working without reintroducing the
        # shared-context attribution bug.
        self._context: TraceContext | None = context
        self._clock = clock

    @property
    def inner(self) -> Transport:
        return self._inner

    @property
    def tracer(self) -> Tracer:
        return self._tracer

    def set_context(self, context: TraceContext) -> None:
        """Bind trace context to this transport, not to a shared tracer."""
        self._context = context

    @property
    def state(self) -> TransportState:
        return self._inner.state

    @property
    def is_open(self) -> bool:
        return self._inner.is_open

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._inner.descriptor

    @property
    def message_based(self) -> bool:
        return bool(getattr(self._inner, "message_based", False))

    def operation_lock(self) -> AbstractContextManager[None]:
        return self._inner.operation_lock()

    def invalidate(self) -> None:
        started = self._clock()
        try:
            self._inner.invalidate()
        except BaseException as exc:
            self._fail(TraceDirection.ERROR, started, exc)
            raise
        self._tracer.emit(
            TraceDirection.ERROR,
            descriptor=self._inner.descriptor,
            context=self._context,
            success=False,
            duration_s=self._clock() - started,
            error=RuntimeError("transport invalidated by protocol layer"),
        )

    def open(self) -> TransportDescriptor:
        started = self._clock()
        try:
            descriptor = self._inner.open()
        except BaseException as exc:
            self._fail(TraceDirection.OPEN, started, exc)
            raise
        self._tracer.emit(
            TraceDirection.OPEN,
            descriptor=descriptor,
            context=self._context,
            duration_s=self._clock() - started,
        )
        return descriptor

    def close(self) -> None:
        started = self._clock()
        descriptor = self._inner.descriptor
        try:
            self._inner.close()
        except BaseException as exc:
            self._fail(TraceDirection.CLOSE, started, exc, descriptor=descriptor)
            raise
        self._tracer.emit(
            TraceDirection.CLOSE,
            descriptor=descriptor,
            context=self._context,
            duration_s=self._clock() - started,
        )

    def __enter__(self) -> InstrumentedTransport:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        started = self._clock()
        try:
            result = self._inner.write(data, timeout_s=timeout_s, operation_id=operation_id)
        except BaseException as exc:
            self._fail(TraceDirection.ERROR, started, exc, data=data, operation_id=operation_id)
            raise
        self._tracer.emit(
            TraceDirection.TX,
            data=data,
            operation_id=operation_id,
            descriptor=self._inner.descriptor,
            context=self._context,
            duration_s=self._clock() - started,
        )
        return result

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes:
        started = self._clock()
        try:
            data = self._inner.read(request, timeout_s=timeout_s, operation_id=operation_id)
        except BaseException as exc:
            self._fail(TraceDirection.RX, started, exc, operation_id=operation_id)
            raise
        self._tracer.emit(
            TraceDirection.RX,
            data=data,
            operation_id=operation_id,
            descriptor=self._inner.descriptor,
            context=self._context,
            duration_s=self._clock() - started,
        )
        return data

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes:
        """Trace one transaction without ever claiming an uncertain write succeeded."""
        started = self._clock()
        with self._inner.operation_lock():
            try:
                data = self._inner.transact(
                    outbound,
                    response,
                    timeout_s=timeout_s,
                    replay_policy=replay_policy,
                    operation_id=operation_id,
                )
            except BaseException as exc:
                # The wrapper cannot know whether a failing backend transaction
                # wrote no bytes, some bytes, or the complete command. Record
                # the outbound attempt as unsuccessful, then the failed receive
                # phase. This preserves phase visibility without a false
                # positive such as "OUTP ON was transmitted successfully".
                self._tracer.emit(
                    TraceDirection.TX,
                    data=outbound,
                    operation_id=operation_id,
                    descriptor=self._inner.descriptor,
                    context=self._context,
                    success=False,
                    duration_s=self._clock() - started,
                    error=exc,
                )
                self._fail(TraceDirection.RX, started, exc, operation_id=operation_id)
                raise
            self._tracer.emit(
                TraceDirection.TX,
                data=outbound,
                operation_id=operation_id,
                descriptor=self._inner.descriptor,
                context=self._context,
            )
            self._tracer.emit(
                TraceDirection.RX,
                data=data,
                operation_id=operation_id,
                descriptor=self._inner.descriptor,
                context=self._context,
                duration_s=self._clock() - started,
            )
            return data

    def flush(self, direction: FlushDirection) -> None:
        started = self._clock()
        try:
            self._inner.flush(direction)
        except BaseException as exc:
            self._fail(TraceDirection.FLUSH, started, exc)
            raise
        self._tracer.emit(
            TraceDirection.FLUSH,
            descriptor=self._inner.descriptor,
            context=self._context,
            duration_s=self._clock() - started,
        )

    def __getattr__(self, name: str) -> Any:
        """Forward optional bus capabilities only when the inner transport has them."""
        if name in _CAPABILITY_NAMES:
            return getattr(self._inner, name)
        raise AttributeError(name)

    def _fail(
        self,
        direction: TraceDirection,
        started: float,
        error: BaseException,
        *,
        data: bytes = b"",
        operation_id: str | None = None,
        descriptor: TransportDescriptor | None = None,
    ) -> None:
        self._tracer.emit(
            direction,
            data=data,
            operation_id=operation_id,
            descriptor=descriptor if descriptor is not None else self._inner.descriptor,
            context=self._context,
            success=False,
            duration_s=self._clock() - started,
            error=error,
        )
