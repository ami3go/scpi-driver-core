"""Framework-independent SCPI/IEEE-488.2 driver infrastructure."""

from scpi_driver_core.exceptions import (
    ConfigurationError,
    IdentityError,
    NotConnectedError,
    OperationTimeoutError,
    ProtocolError,
    ResponseParseError,
    SafetyGuardError,
    ScpiCommandError,
    ScpiDriverError,
    ScpiErrorQueueError,
    ScpiTimeoutError,
    SessionClosedError,
    TransportError,
    TransportTimeoutError,
    UnsupportedOperationError,
)
from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.session import ScpiSession, SessionHealth, SessionRegistry

__all__ = [
    "ConfigurationError",
    "IdentityError",
    "NotConnectedError",
    "OperationTimeoutError",
    "ProtocolError",
    "ResponseParseError",
    "SafetyGuardError",
    "ScpiClient",
    "ScpiCommandError",
    "ScpiDriverError",
    "ScpiErrorQueueError",
    "ScpiSession",
    "ScpiTimeoutError",
    "SessionClosedError",
    "SessionHealth",
    "SessionRegistry",
    "TransportError",
    "TransportTimeoutError",
    "UnsupportedOperationError",
]

__version__ = "0.1.0.dev6"
