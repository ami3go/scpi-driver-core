"""Exception hierarchy for keysight_n6700.

Names intentionally do not shadow built-in ConnectionError/TimeoutError.
"""

from __future__ import annotations

from collections.abc import Sequence

from .types import ScpiErrorRecord


class N6700Error(Exception):
    """Base class for all package errors."""


class N6700ConnectionError(N6700Error):
    """The driver could not open or maintain a connection."""


class N6700TimeoutError(N6700Error):
    """A transport or instrument operation timed out."""


class N6700CommunicationError(N6700Error):
    """A generic transport or protocol communication error occurred."""


class N6700CommandError(N6700Error):
    """The instrument rejected a command or reported a SCPI error."""

    def __init__(self, message: str, errors: Sequence[ScpiErrorRecord] | None = None) -> None:
        self.errors = tuple(errors or ())
        if self.errors:
            detail = "; ".join(f"{err.code}: {err.message}" for err in self.errors)
            message = f"{message} | SCPI errors: {detail}"
        super().__init__(message)


class N6700ProtectionError(N6700CommandError):
    """A protection event or safety interlock prevented an operation."""


class N6700QueryInterruptedError(N6700CommandError):
    """A query was interrupted or another command was sent before reading the response."""


class UnsupportedFeatureError(N6700Error):
    """The installed module, transport, or verified command set does not support a feature."""


class InvalidChannelError(N6700Error):
    """A channel outside the installed range was requested."""


class SafetyInterlockError(N6700ProtectionError):
    """A safety interlock or inhibit condition is active."""
