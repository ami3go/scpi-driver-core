"""The transport state machine, shared by every backend.

The state machine owns lifecycle, serialization, invalidation and the rule that
an interrupted exchange cannot leave a transport apparently healthy. Backend
classes only acquire/release their concrete resource and implement I/O.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from types import TracebackType
from typing import TypeVar

from scpi_driver_core.exceptions import NotConnectedError, _attach_cleanup_error
from scpi_driver_core.transport.models import TransportDescriptor, TransportState

__all__ = ["TransportStateMachine"]

_TSelf = TypeVar("_TSelf", bound="TransportStateMachine")


class TransportStateMachine:
    """Lifecycle and state for a byte transport.

    ``_lock`` serializes lifecycle and I/O. State introspection deliberately
    uses a separate tiny lock, so dashboards and shutdown logic do not wait for
    a long waveform transfer merely to ask whether a resource is open.
    """

    def __init__(self, descriptor: TransportDescriptor) -> None:
        self._descriptor = descriptor
        self._state = TransportState.CREATED
        self._state_lock = threading.Lock()
        self._lock = threading.RLock()

    @property
    def state(self) -> TransportState:
        with self._state_lock:
            return self._state

    @property
    def is_open(self) -> bool:
        """Whether the backend resource is held. Says nothing about the instrument."""
        return self.state is TransportState.OPEN

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._descriptor

    def operation_lock(self) -> AbstractContextManager[None]:
        """Hold this transport's serialization lock across several operations."""
        return self._operation_lock()

    @contextmanager
    def _operation_lock(self) -> Iterator[None]:
        with self._lock:
            yield

    def close(self) -> None:
        """Release the resource.

        A successful close is idempotent. If release fails, ownership is
        uncertain and the transport moves to ``FAULTED``; the cleanup error
        propagates and a later explicit close/open may retry release.
        """
        with self._lock:
            if self.state in (TransportState.CREATED, TransportState.CLOSED):
                return
            self._set_state(TransportState.CLOSING)
            try:
                self._release_resource()
                self._on_closed()
            except BaseException:
                self._set_state(TransportState.FAULTED)
                raise
            self._set_state(TransportState.CLOSED)

    def invalidate(self) -> None:
        """Declare connection framing/state unusable and move to ``FAULTED``."""
        with self._lock:
            if self.state is TransportState.OPEN:
                self._fault()

    def _fault(self) -> None:
        """Release the resource and record uncertain session validity."""
        try:
            self._release_resource()
            self._on_closed()
        finally:
            self._set_state(TransportState.FAULTED)

    @contextmanager
    def _faulting_io(self) -> Iterator[None]:
        """Fault if *anything* escapes and retain any cleanup failure."""
        try:
            yield
        except BaseException as primary:
            try:
                self._fault()
            except BaseException as cleanup:
                _attach_cleanup_error(primary, cleanup)
            raise

    def _require_state_open(self) -> None:
        """Refuse I/O before anything is transmitted."""
        state = self.state
        if state is not TransportState.OPEN:
            raise NotConnectedError(f"transport is {state.name}, not OPEN")

    def __enter__(self: _TSelf) -> _TSelf:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc is None:
            self.close()
            return
        try:
            self.close()
        except BaseException as cleanup:
            _attach_cleanup_error(exc, cleanup)

    def open(self) -> TransportDescriptor:
        """Acquire the backend resource."""
        raise NotImplementedError

    def _set_state(self, state: TransportState) -> None:
        """The single place state changes, so subclasses can observe transitions."""
        with self._state_lock:
            self._state = state

    def _release_resource(self) -> None:
        """Release the backend resource. Must tolerate being called twice."""
        raise NotImplementedError

    def _on_closed(self) -> None:
        """Discard anything tied to the connection, such as buffered data."""
