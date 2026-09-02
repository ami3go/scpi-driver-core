"""Framework-independent SCPI/IEEE-488.2 driver infrastructure.

The public API is implemented according to
``task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md``. The error hierarchy is
re-exported here because catching ``ScpiDriverError`` is the one import every
consumer needs, regardless of which subsystem it uses.
"""

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
    TransportError,
    TransportTimeoutError,
    UnsupportedOperationError,
)

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

__version__ = "0.1.0.dev0"
