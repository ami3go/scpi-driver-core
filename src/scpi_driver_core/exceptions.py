"""Common exception hierarchy for SCPI driver infrastructure.

Concrete drivers may subclass these errors. Backend exceptions raised by
transport libraries are translated into this hierarchy with ``raise ... from``
so the original cause is preserved.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scpi_driver_core.models import ScpiError

__all__ = [
    "ConfigurationError",
    "IdentityError",
    "NotConnectedError",
    "OperationTimeoutError",
    "ProtocolError",
    "ResponseParseError",
    "SafetyGuardError",
    "ScpiCommandError",
    "ScpiDriverError",
    "ScpiErrorQueueError",
    "ScpiTimeoutError",
    "SessionClosedError",
    "TransportError",
    "TransportTimeoutError",
    "UnsupportedOperationError",
]


class ScpiDriverError(Exception):
    """Base class for every error raised by ``scpi_driver_core``."""


class ConfigurationError(ScpiDriverError):
    """Invalid or inconsistent configuration supplied by the caller."""


class ScpiTimeoutError(ScpiDriverError):
    """Base class for every bounded wait that expires."""


class TransportError(ScpiDriverError):
    """Failure in the byte-oriented transport layer."""


class NotConnectedError(TransportError):
    """I/O was attempted while the transport was not open."""


class TransportTimeoutError(TransportError, ScpiTimeoutError):
    """A transport operation exceeded its timeout."""


class ProtocolError(ScpiDriverError):
    """The instrument response violated the expected protocol."""


class ResponseParseError(ProtocolError):
    """A response could not be parsed into the requested type.

    The offending response is retained on ``raw`` so a caller can report what
    the instrument actually sent, which is frequently the only clue available
    when a device deviates from its documented format.
    """

    def __init__(self, message: str, *, raw: str | bytes | None = None) -> None:
        super().__init__(message)
        self.raw = raw


class ScpiCommandError(ProtocolError):
    """A SCPI command was rejected or could not be executed."""


class ScpiErrorQueueError(ScpiDriverError):
    """The instrument reported one or more entries in its SCPI error queue.

    ``errors`` contains every entry that was removed from the instrument before
    this exception was raised. ``complete`` is false if collection stopped at a
    configured bound or on an unparsable queue reply.
    """

    def __init__(
        self,
        message: str,
        *,
        errors: Sequence[ScpiError] = (),
        complete: bool = True,
    ) -> None:
        super().__init__(message)
        self.errors = tuple(errors)
        self.complete = complete


class IdentityError(ScpiDriverError):
    """An ``*IDN?`` reply was missing, unparsable, or unacceptable."""


class OperationTimeoutError(ScpiTimeoutError):
    """A bounded higher-level operation (polling, completion wait) expired."""


class SessionClosedError(ScpiDriverError):
    """Automatic recovery was requested for a session not faulted by I/O.

    Deliberately closed or never-opened sessions are never silently reopened by
    retry machinery. Call :meth:`ScpiSession.open` explicitly instead.
    """


class UnsupportedOperationError(ScpiDriverError):
    """The requested operation is not supported by this transport or instrument."""


class SafetyGuardError(ScpiDriverError):
    """A guarded operation was attempted without the required confirmation."""
