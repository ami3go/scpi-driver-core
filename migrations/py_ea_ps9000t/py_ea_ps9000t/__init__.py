"""Typed core driver for the Elektro-Automatik EA-PS 9000 T DC laboratory power supply."""

from .driver import EaPs9000T
from .enums import AlarmAction, OutputRestoreMode, PowerStageAfterRemote, RemoteControlOwner
from .exceptions import (
    EaPs9000TConfigurationError,
    EaPs9000TConnectionError,
    EaPs9000TDeviceError,
    EaPs9000TError,
    EaPs9000TProtocolError,
    EaPs9000TTimeoutError,
    EaPs9000TValidationError,
)
from .models import (
    AdjustmentLimits,
    AlarmCounters,
    ConnectionState,
    InstrumentIdentity,
    MeasuredValues,
    NominalRatings,
    ProtectionThresholds,
)
from .simulator import SimEaPs9000TInstrument

__version__ = "26.2"

__all__ = [
    "AdjustmentLimits",
    "AlarmAction",
    "AlarmCounters",
    "ConnectionState",
    "EaPs9000T",
    "EaPs9000TConfigurationError",
    "EaPs9000TConnectionError",
    "EaPs9000TDeviceError",
    "EaPs9000TError",
    "EaPs9000TProtocolError",
    "EaPs9000TTimeoutError",
    "EaPs9000TValidationError",
    "InstrumentIdentity",
    "MeasuredValues",
    "NominalRatings",
    "OutputRestoreMode",
    "PowerStageAfterRemote",
    "ProtectionThresholds",
    "RemoteControlOwner",
    "SimEaPs9000TInstrument",
    "__version__",
]
