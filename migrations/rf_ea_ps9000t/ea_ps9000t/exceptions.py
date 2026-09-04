"""RFDS-007 exception hierarchy for the EA-PS 9000 T core driver.

Every exception is rooted in :class:`EaPs9000TError`. Nothing in this
package raises a bare built-in exception at a public boundary.
"""

from __future__ import annotations


class EaPs9000TError(Exception):
    """Base class for all errors raised by :mod:`ea_ps9000t`."""


class EaPs9000TConfigurationError(EaPs9000TError):
    """A connection or driver configuration value is invalid."""


class EaPs9000TValidationError(EaPs9000TError):
    """A keyword/method argument failed validation before any device I/O."""


class EaPs9000TConnectionError(EaPs9000TError):
    """The transport could not be opened, is not open when required, or remote
    control could not be acquired/was lost (task §6 item 1).

    Remote-control refusal is modeled as a connection-level failure, not a
    generic device error, because a session without remote control cannot
    meaningfully do anything this driver exposes.
    """


class EaPs9000TTimeoutError(EaPs9000TError):
    """A transport read or write did not complete within its timeout."""


class EaPs9000TProtocolError(EaPs9000TError):
    """A response was malformed or inconsistent with what was expected."""


class EaPs9000TDeviceError(EaPs9000TError):
    """The instrument reported an error through its SCPI error queue."""
