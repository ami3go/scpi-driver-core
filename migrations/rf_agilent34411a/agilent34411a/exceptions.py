"""RFDS-007 exception hierarchy for the Agilent 34411A core driver.

Every exception is rooted in :class:`Agilent34411AError`. Nothing in this
package raises a bare built-in exception at a public boundary.
"""

from __future__ import annotations


class Agilent34411AError(Exception):
    """Base class for all errors raised by :mod:`agilent34411a`."""


class Agilent34411AConfigurationError(Agilent34411AError):
    """A connection or driver configuration value is invalid.

    Also raised when the instrument is not in native 34411A SCPI language
    mode (``SYSTem:LANguage``) — task §6 item 7.
    """


class Agilent34411AValidationError(Agilent34411AError):
    """A keyword/method argument failed validation before any device I/O."""


class Agilent34411AConnectionError(Agilent34411AError):
    """The transport could not be opened, or is not open when required."""


class Agilent34411ATimeoutError(Agilent34411AError):
    """A transport read or write did not complete within its timeout."""


class Agilent34411AProtocolError(Agilent34411AError):
    """A response was malformed or inconsistent with what was expected."""


class Agilent34411ADeviceError(Agilent34411AError):
    """The instrument reported an error through its error/event queue."""


class Agilent34411AOverloadError(Agilent34411ADeviceError):
    """A reading returned the documented overload sentinel (+/-9.9E+37).

    Distinct from a generic device error: this is a specific, documented
    out-of-range condition (task §6 item 3), not an arbitrary SCPI fault.
    """
