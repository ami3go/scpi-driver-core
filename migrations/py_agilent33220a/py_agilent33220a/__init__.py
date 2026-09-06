"""Typed core driver for the Agilent (Keysight) 33220A function/arbitrary waveform generator."""

from .driver import Agilent33220A
from .enums import (
    AmplitudeUnit,
    AngleUnit,
    BurstMode,
    FrontPanelLockExclude,
    Function,
    GatePolarity,
    ModulatingShape,
    ModulationSource,
    OutputPolarity,
    SweepSpacing,
    TriggerSlope,
    TriggerSource,
)
from .exceptions import (
    Agilent33220AConfigurationError,
    Agilent33220AConnectionError,
    Agilent33220ADeviceError,
    Agilent33220AError,
    Agilent33220AProtocolError,
    Agilent33220ASafetyError,
    Agilent33220ATimeoutError,
    Agilent33220AValidationError,
)
from .models import (
    ArbWaveformAttributes,
    ConnectionState,
    InstrumentIdentity,
    OutputSettings,
    TriggerSettings,
)
from .simulator import SimAgilent33220AInstrument

__version__ = "26.2"

__all__ = [
    "Agilent33220A",
    "Agilent33220AConfigurationError",
    "Agilent33220AConnectionError",
    "Agilent33220ADeviceError",
    "Agilent33220AError",
    "Agilent33220AProtocolError",
    "Agilent33220ASafetyError",
    "Agilent33220ATimeoutError",
    "Agilent33220AValidationError",
    "AmplitudeUnit",
    "AngleUnit",
    "ArbWaveformAttributes",
    "BurstMode",
    "ConnectionState",
    "FrontPanelLockExclude",
    "Function",
    "GatePolarity",
    "InstrumentIdentity",
    "ModulatingShape",
    "ModulationSource",
    "OutputPolarity",
    "OutputSettings",
    "SimAgilent33220AInstrument",
    "SweepSpacing",
    "TriggerSettings",
    "TriggerSlope",
    "TriggerSource",
    "__version__",
]
