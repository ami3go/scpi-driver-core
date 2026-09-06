"""Python driver for RP2040 W5500 E-Resistor board."""
from __future__ import annotations

from .client import EResistorClient
from .discovery import discover_boards, discover_boards_auto
from .models import (
    BoardInfo,
    BranchCalibration,
    CalibrationConfig,
    ChannelCalibration,
    ConnectionLossPolicy,
    ConnectionState,
    DeviceCalibration,
    DeviceProfile,
    OutputSnapshot,
    ReconnectConfig,
    ReconnectStatePolicy,
    SafetyConfig,
    SetResistanceResult,
    SetTemperatureResult,
    ShutdownPolicy,
    WatchdogConfig,
)
from .temperature import TemperatureTable
from .simulation import CurveProfile, CurveSimulation

__all__ = [
    "EResistorClient",
    "discover_boards",
    "discover_boards_auto",
    "BoardInfo",
    "BranchCalibration",
    "CalibrationConfig",
    "ChannelCalibration",
    "ConnectionLossPolicy",
    "ConnectionState",
    "DeviceCalibration",
    "DeviceProfile",
    "OutputSnapshot",
    "ReconnectConfig",
    "ReconnectStatePolicy",
    "SafetyConfig",
    "SetResistanceResult",
    "SetTemperatureResult",
    "ShutdownPolicy",
    "TemperatureTable",
    "WatchdogConfig",
    "CurveProfile",
    "CurveSimulation",
]

__version__ = "0.1.1"
