"""Typed core driver for the Tektronix TBS1000C series oscilloscopes."""

from .driver import Tbs1000c
from .enums import (
    AcquisitionMode,
    Coupling,
    ImageFormat,
    ImageLayout,
    MeasurementType,
    TriggerCoupling,
    TriggerSlope,
)
from .exceptions import (
    Tbs1000cCalibrationError,
    Tbs1000cConfigurationError,
    Tbs1000cConnectionError,
    Tbs1000cDeviceError,
    Tbs1000cError,
    Tbs1000cProtocolError,
    Tbs1000cTimeoutError,
    Tbs1000cValidationError,
)
from .models import (
    CalibrationStatus,
    ChannelSettings,
    ConnectionState,
    InstrumentIdentity,
    TriggerSettings,
    Waveform,
    WaveformPreamble,
)
from .simulator import SimTbs1000cInstrument

__version__ = "26.2"

__all__ = [
    "AcquisitionMode",
    "CalibrationStatus",
    "ChannelSettings",
    "ConnectionState",
    "Coupling",
    "ImageFormat",
    "ImageLayout",
    "InstrumentIdentity",
    "MeasurementType",
    "SimTbs1000cInstrument",
    "Tbs1000c",
    "Tbs1000cCalibrationError",
    "Tbs1000cConfigurationError",
    "Tbs1000cConnectionError",
    "Tbs1000cDeviceError",
    "Tbs1000cError",
    "Tbs1000cProtocolError",
    "Tbs1000cTimeoutError",
    "Tbs1000cValidationError",
    "TriggerCoupling",
    "TriggerSettings",
    "TriggerSlope",
    "Waveform",
    "WaveformPreamble",
    "__version__",
]
