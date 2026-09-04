"""RFDS-007 exception hierarchy for the TBS1000C core driver.

Every exception is rooted in :class:`Tbs1000cError`. Nothing in this package
raises a bare built-in exception at a public boundary.
"""

from __future__ import annotations


class Tbs1000cError(Exception):
    """Base class for all errors raised by :mod:`tbs1000c`."""


class Tbs1000cConfigurationError(Tbs1000cError):
    """A connection or driver configuration value is invalid."""


class Tbs1000cValidationError(Tbs1000cError):
    """A keyword/method argument failed validation before any device I/O."""


class Tbs1000cConnectionError(Tbs1000cError):
    """The transport could not be opened, or is not open when required."""


class Tbs1000cTimeoutError(Tbs1000cError):
    """A transport read or write did not complete within its timeout."""


class Tbs1000cProtocolError(Tbs1000cError):
    """A response was malformed, truncated, or inconsistent with its preamble."""


class Tbs1000cDeviceError(Tbs1000cError):
    """The instrument reported an error through its event/status queue."""


class Tbs1000cCalibrationError(Tbs1000cDeviceError):
    """Internal calibration failed, or a keyword was blocked while one is running."""
