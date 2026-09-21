"""The transport state machine, shared by every backend.

The state machine owns lifecycle, serialization, invalidation and the rule that
an interrupted exchange cannot leave a transport apparently healthy. Backend
classes only acquire/release their concrete resource and implement I/O.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from types import TracebackType
from typing import Self

from scpi_driver_core.exceptions import NotConnectedError
from scpi_driver_core.transport.models import TransportDescriptor, TransportState

__all__ = ["TransportStateMachine"]


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

    # -- introspection ----------------------------------------------------

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

    # -- lifecycle --------------------------------------------------------

    def close(self) -> None:
        """Release the resource. Idempotent, and always reaches ``CLOSED``."""
        with self._lock:
            if self.state in (TransportState.CREATED, TransportState.CLOSED):
                return
            self._set_state(TransportState.CLOSING)
            try:
                self._release_resource()
            finally:
                self._on_closed()
                self._set_state(TransportState.CLOSED)

    def invalidate(self) -> None:
        """Declare connection framing/state unusable and move to ``FAULTED``.

        Protocol layers call this after partially consuming a response whose
        framing later proves invalid. Reusing that byte stream could otherwise
        turn leftovers into the next command's apparently valid response.
        """
        with self._lock:
            if self.state is TransportState.OPEN:
                self._fault()

    def _fault(self) -> None:
        """Release the resource and record uncertain session validity.

        ``FAULTED`` is reached even if backend cleanup itself fails. Cleanup
        errors may still propagate to an explicit caller, but the state can
        never remain incorrectly ``OPEN`` or ``CLOSING``.
        """
        try:
            self._release_resource()
        finally:
            self._on_closed()
            self._set_state(TransportState.FAULTED)

    @contextmanager
    def _faulting_io(self) -> Iterator[None]:
        """Fault if *anything* escapes an exchange, including ``BaseException``.

        Ctrl+C, ``SystemExit`` and signal-mode watchdog exceptions can interrupt
        after a query was transmitted but before its reply was consumed. The
        original exception is re-raised unchanged after best-effort invalidation.
        """
        try:
            yield
        except BaseException:
            with suppress(Exception):
                self._fault()
            raise

    def _require_state_open(self) -> None:
        """Refuse I/O before anything is transmitted."""
        state = self.state
        if state is not TransportState.OPEN:
            raise NotConnectedError(f"transport is {state.name}, not OPEN")

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    # -- hooks ------------------------------------------------------------

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
