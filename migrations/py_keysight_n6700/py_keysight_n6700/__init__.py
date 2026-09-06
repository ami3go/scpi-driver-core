"""Safe Python driver for Keysight/Agilent N6700 modular power systems."""

from .capabilities import ChannelCapabilities, ModuleType, classify_module
from .channel import BaseChannel, ElectronicLoadChannel, PowerSupplyChannel, SMUChannel
from .driver import N6700
from .exceptions import (
    InvalidChannelError,
    N6700CommandError,
    N6700CommunicationError,
    N6700ConnectionError,
    N6700Error,
    N6700ProtectionError,
    N6700QueryInterruptedError,
    N6700TimeoutError,
    SafetyInterlockError,
    UnsupportedFeatureError,
)
from .simulator import SimN6700Instrument
from .transport import PyVisaTransport, RawSocketTransport, SimulatedTransport, Transport
from .types import (
    ArrayMeasurement,
    InstrumentIdentity,
    Measurement,
    PowerMeasurement,
    ProtectionClearResult,
    ProtectionStatus,
    RemoteState,
    ScpiErrorRecord,
    ShutdownResult,
)

__all__ = [
    "N6700",
    "Transport",
    "PyVisaTransport",
    "RawSocketTransport",
    "SimulatedTransport",
    "SimN6700Instrument",
    "BaseChannel",
    "PowerSupplyChannel",
    "SMUChannel",
    "ElectronicLoadChannel",
    "ChannelCapabilities",
    "ModuleType",
    "classify_module",
    "InstrumentIdentity",
    "ScpiErrorRecord",
    "Measurement",
    "PowerMeasurement",
    "ProtectionStatus",
    "ProtectionClearResult",
    "ArrayMeasurement",
    "RemoteState",
    "ShutdownResult",
    "N6700Error",
    "N6700ConnectionError",
    "N6700TimeoutError",
    "N6700CommunicationError",
    "N6700CommandError",
    "N6700ProtectionError",
    "N6700QueryInterruptedError",
    "UnsupportedFeatureError",
    "InvalidChannelError",
    "SafetyInterlockError",
]
