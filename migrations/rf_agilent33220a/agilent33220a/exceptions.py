"""RFDS-007 exception hierarchy for the Agilent 33220A core driver.

Every exception is rooted in :class:`Agilent33220AError`. Nothing in this
package raises a bare built-in exception at a public boundary.
"""

from __future__ import annotations


class Agilent33220AError(Exception):
    """Base class for all errors raised by :mod:`agilent33220a`."""


class Agilent33220AConfigurationError(Agilent33220AError):
    """A connection or driver configuration value is invalid."""


class Agilent33220AValidationError(Agilent33220AError):
    """A keyword/method argument failed validation before any device I/O."""


class Agilent33220AConnectionError(Agilent33220AError):
    """The transport could not be opened, or is not open when required."""


class Agilent33220ATimeoutError(Agilent33220AError):
    """A transport read or write did not complete within its timeout."""


class Agilent33220AProtocolError(Agilent33220AError):
    """A response was malformed or inconsistent with what was expected."""


class Agilent33220ADeviceError(Agilent33220AError):
    """The instrument reported an error through its error/event queue."""


class Agilent33220ASafetyError(Agilent33220AError):
    """A documented physical/signal-integrity limit was violated (RFDS-007 LimitViolation).

    Distinct from :class:`Agilent33220AValidationError`: this is for real
    signal-integrity constraints (e.g. the amplitude/offset relationship),
    not arbitrary argument-shape checks.
    """
