"""Common exception hierarchy for SCPI driver infrastructure.

Concrete drivers may subclass these errors. Backend exceptions raised by
transport libraries are translated into this hierarchy with ``raise ... from``
so the original cause is preserved.
"""

from __future__ import annotations

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
    "TransportError",
    "TransportTimeoutError",
    "UnsupportedOperationError",
]


class ScpiDriverError(Exception):
    """Base class for every error raised by ``scpi_driver_core``."""


class ConfigurationError(ScpiDriverError):
    """Invalid or inconsistent configuration supplied by the caller."""


class TransportError(ScpiDriverError):
    """Failure in the byte-oriented transport layer."""


class NotConnectedError(TransportError):
    """I/O was attempted while the transport was not open."""


class TransportTimeoutError(TransportError):
    """A transport operation exceeded its timeout."""


class ProtocolError(ScpiDriverError):
    """The instrument response violated the expected protocol."""


class ResponseParseError(ProtocolError):
    """A response could not be parsed into the requested type.

    The offending response is retained on ``raw`` so a caller can report what
    the instrument actually sent, which is frequently the only clue available
    when a device deviates from its documented format.

    Args:
        message: description of what could not be parsed.
        raw: the unmodified response, when available.
    """

    def __init__(self, message: str, *, raw: str | bytes | None = None) -> None:
        super().__init__(message)
        self.raw = raw


class ScpiCommandError(ProtocolError):
    """A SCPI command was rejected or could not be executed."""


class ScpiErrorQueueError(ScpiDriverError):
    """The instrument reported one or more entries in its SCPI error queue."""


class IdentityError(ScpiDriverError):
    """An ``*IDN?`` reply was missing, unparsable, or unacceptable."""


class OperationTimeoutError(ScpiDriverError):
    """A bounded operation (polling, completion wait) exceeded its deadline."""


class UnsupportedOperationError(ScpiDriverError):
    """The requested operation is not supported by this transport or instrument."""


class SafetyGuardError(ScpiDriverError):
    """A guarded operation was attempted without the required confirmation."""
