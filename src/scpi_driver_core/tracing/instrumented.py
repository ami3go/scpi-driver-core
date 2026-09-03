"""A transport wrapper that traces everything passing through it.

Instrumenting here rather than in each backend means TCP, UDP, serial, VISA and
mock are all traced by one implementation, and a backend added later is traced
without touching it. The wrapper satisfies the
:class:`~scpi_driver_core.transport.base.Transport` protocol itself, so it drops
in wherever a transport is expected, including underneath ``ScpiClient``.

Tracing never changes behavior. Payloads are passed through byte for byte,
exceptions propagate unchanged after being recorded, and an observer that
misbehaves cannot break instrument I/O.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from scpi_driver_core.tracing.events import TraceDirection
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


class InstrumentedTransport:
    """Wraps a transport and emits a trace event for each operation.

    Args:
        inner: the transport actually doing the work.
        tracer: where events go.
        clock: monotonic source used for durations; injectable for tests.
    """

    def __init__(
        self,
        inner: Transport,
        tracer: Tracer,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._inner = inner
        self._tracer = tracer
        self._clock = clock

    @property
    def inner(self) -> Transport:
        """The wrapped transport, for a driver that needs backend specifics."""
        return self._inner

    @property
    def tracer(self) -> Tracer:
        return self._tracer

    # -- introspection is not traced --------------------------------------

    @property
    def state(self) -> TransportState:
        return self._inner.state

    @property
    def is_open(self) -> bool:
        return self._inner.is_open

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._inner.descriptor

    # -- lifecycle --------------------------------------------------------

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
            duration_s=self._clock() - started,
        )

    # -- I/O --------------------------------------------------------------

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
            self._fail(TraceDirection.TX, started, exc, data=data, operation_id=operation_id)
            raise
        self._tracer.emit(
            TraceDirection.TX,
            data=data,
            operation_id=operation_id,
            descriptor=self._inner.descriptor,
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
        """Trace the write and the read as two events under one operation id.

        The halves are recorded separately because that is what a reader needs
        in order to see which one failed, while ``operation_id`` keeps them
        correlated.
        """
        started = self._clock()
        self._tracer.emit(
            TraceDirection.TX,
            data=outbound,
            operation_id=operation_id,
            descriptor=self._inner.descriptor,
        )
        try:
            data = self._inner.transact(
                outbound,
                response,
                timeout_s=timeout_s,
                replay_policy=replay_policy,
                operation_id=operation_id,
            )
        except BaseException as exc:
            self._fail(TraceDirection.RX, started, exc, operation_id=operation_id)
            raise
        self._tracer.emit(
            TraceDirection.RX,
            data=data,
            operation_id=operation_id,
            descriptor=self._inner.descriptor,
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
            duration_s=self._clock() - started,
        )

    # -- internals --------------------------------------------------------

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
            success=False,
            duration_s=self._clock() - started,
            error=error,
        )
