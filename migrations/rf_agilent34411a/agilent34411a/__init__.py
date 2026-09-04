"""Typed core driver for the Agilent (Keysight) 34411A 6.5-digit digital multimeter."""

from .driver import Agilent34411A
from .enums import (
    AcFilter,
    AutoZeroMode,
    Function,
    MathFunction,
    SampleSource,
    TemperatureProbeType,
    TemperatureUnit,
    ThermistorType,
    TriggerSlope,
    TriggerSource,
)
from .exceptions import (
    Agilent34411AConfigurationError,
    Agilent34411AConnectionError,
    Agilent34411ADeviceError,
    Agilent34411AError,
    Agilent34411AOverloadError,
    Agilent34411AProtocolError,
    Agilent34411ATimeoutError,
    Agilent34411AValidationError,
)
from .models import (
    ConnectionState,
    InstrumentIdentity,
    MeasurementSettings,
    StatisticsResult,
    TriggerSettings,
)
from .simulator import SimAgilent34411AInstrument

__version__ = "26.2"

__all__ = [
    "AcFilter",
    "Agilent34411A",
    "Agilent34411AConfigurationError",
    "Agilent34411AConnectionError",
    "Agilent34411ADeviceError",
    "Agilent34411AError",
    "Agilent34411AOverloadError",
    "Agilent34411AProtocolError",
    "Agilent34411ATimeoutError",
    "Agilent34411AValidationError",
    "AutoZeroMode",
    "ConnectionState",
    "Function",
    "InstrumentIdentity",
    "MathFunction",
    "MeasurementSettings",
    "SampleSource",
    "SimAgilent34411AInstrument",
    "StatisticsResult",
    "TemperatureProbeType",
    "TemperatureUnit",
    "ThermistorType",
    "TriggerSettings",
    "TriggerSlope",
    "TriggerSource",
    "__version__",
]
