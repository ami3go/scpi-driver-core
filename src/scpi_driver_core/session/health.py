"""Communication health, tracked separately from transport state.

A transport being open says only that a socket or session handle is held. It
says nothing about whether the instrument at the other end is answering: a
powered-down instrument on a live TCP connection is open and mute. So a session
can truthfully report ``connected=True`` alongside ``communication_ok=False``,
and the two are never collapsed into one flag.

``communication_ok`` is deliberately tri-state. ``None`` means nobody has asked
the instrument anything yet, which is not the same as having asked and been
answered, nor as having asked and been ignored.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from scpi_driver_core.exceptions import ScpiDriverError

__all__ = ["SessionHealth"]


@dataclass
class SessionHealth:
    """What is known about a session's connection and responsiveness.

    Timestamps are monotonic, so they stay meaningful across a system clock
    adjustment and are only ever compared with each other.
    """

    connected: bool = False
    communication_ok: bool | None = None
    last_success_monotonic: float | None = None
    last_failure_monotonic: float | None = None
    last_error: ScpiDriverError | None = None

    def record_connected(self) -> None:
        """Note that the transport was opened.

        Responsiveness reverts to unknown rather than optimistically true:
        holding a resource is not evidence that anything replies on it.
        """
        self.connected = True
        self.communication_ok = None

    def record_disconnected(self) -> None:
        """Note that the transport was closed, deliberately or otherwise."""
        self.connected = False
        self.communication_ok = None

    def record_success(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        """Note that the instrument answered."""
        self.communication_ok = True
        self.last_success_monotonic = clock()
        self.last_error = None

    def record_failure(
        self, error: ScpiDriverError, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Note that the instrument did not answer, and why.

        The transport may well still be open; this records only that talking to
        the device failed.
        """
        self.communication_ok = False
        self.last_failure_monotonic = clock()
        self.last_error = error
