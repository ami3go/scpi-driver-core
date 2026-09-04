"""The transport state machine, shared by every backend.

Extracted once TCP, UDP, serial, VISA and mock had all grown byte-for-byte
identical copies of it. The rules it encodes are safety rules rather than
conveniences, so four independent copies were four chances to get one subtly
wrong.

A backend supplies only what is genuinely its own: how to acquire its resource,
how to release it, and what to discard on close.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from scpi_driver_core.exceptions import NotConnectedError
from scpi_driver_core.transport.models import TransportDescriptor, TransportState

__all__ = ["TransportStateMachine"]


class TransportStateMachine:
    """Lifecycle and state for a byte transport.

    Subclasses implement :meth:`_release_resource`, and override
    :meth:`_on_closed` if they hold buffered data.
    """

    def __init__(self, descriptor: TransportDescriptor) -> None:
        self._descriptor = descriptor
        self._state = TransportState.CREATED
        self._lock = threading.RLock()

    # -- introspection, which never performs I/O ---------------------------

    @property
    def state(self) -> TransportState:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        """Whether the backend resource is held. Says nothing about the instrument."""
        return self.state is TransportState.OPEN

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._descriptor

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """Hold this transport's lock across several operations."""
        with self._lock:
            yield

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Release the resource. Idempotent.

        The transport reaches :attr:`TransportState.CLOSED` even if releasing
        raises, and the failure still propagates. Leaving it in ``CLOSING``
        would strand it in a state nothing transitions out of.
        """
        with self._lock:
            if self._state in (TransportState.CREATED, TransportState.CLOSED):
                return
            self._set_state(TransportState.CLOSING)
            try:
                self._release_resource()
            finally:
                self._on_closed()
                self._set_state(TransportState.CLOSED)

    def _fault(self) -> None:
        """Record that an I/O failure left session validity uncertain."""
        self._release_resource()
        self._set_state(TransportState.FAULTED)

    def _require_state_open(self) -> None:
        """Refuse I/O before anything is transmitted.

        Raises:
            NotConnectedError: if the transport is not open.
        """
        if self._state is not TransportState.OPEN:
            raise NotConnectedError(f"transport is {self._state.name}, not OPEN")

    # -- hooks -------------------------------------------------------------

    def _set_state(self, state: TransportState) -> None:
        """The single place state changes, so a subclass can observe every one."""
        self._state = state

    def _release_resource(self) -> None:
        """Release the backend resource. Must tolerate being called twice."""
        raise NotImplementedError

    def _on_closed(self) -> None:
        """Discard anything tied to the connection, such as buffered data."""
