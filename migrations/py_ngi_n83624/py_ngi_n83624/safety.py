"""Validation and safety helpers for NGI N83624."""

from __future__ import annotations

import ipaddress
import math
from collections.abc import Iterable
from enum import IntEnum

from .exceptions import SafetyError, ValidationError
from .models import (
    CaptureRate,
    ChannelLimits,
    CurrentRange,
    FaultSimulationMode,
    LanConnectionType,
    Language,
    OutputMode,
)

SERIAL_BAUDRATES = {9600, 19200, 38400, 57600, 115200}


def validate_channel(channel: int, *, allow_zero: bool = False) -> int:
    low = 0 if allow_zero else 1
    if not isinstance(channel, int) or isinstance(channel, bool) or not (low <= channel <= 24):
        range_text = "0..24" if allow_zero else "1..24"
        raise ValidationError(f"Channel must be an integer in range {range_text}; got {channel!r}")
    return channel


def validate_channels(channels: Iterable[int]) -> list[int]:
    result = [validate_channel(ch) for ch in channels]
    if not result:
        raise ValidationError("Channel list must not be empty")
    if len(set(result)) != len(result):
        raise ValidationError(f"Channel list must contain unique channels; got {result!r}")
    return result


def validate_int_range(name: str, value: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not (minimum <= value <= maximum):
        raise ValidationError(f"{name} must be integer in range {minimum}..{maximum}; got {value!r}")
    return value


def validate_float(name: str, value: float | int, *, allow_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{name} must be int or float; got {type(value).__name__}")
    result = float(value)
    if not math.isfinite(result):
        raise ValidationError(f"{name} must be finite; got {value!r}")
    if result < 0 and not allow_negative:
        raise ValidationError(f"{name} must be non-negative; got {value!r}")
    return result


def validate_enum(enum_type: type[IntEnum], value: IntEnum | int, name: str) -> IntEnum:
    try:
        return enum_type(int(value))
    except (ValueError, TypeError) as exc:
        allowed = ", ".join(str(int(item)) for item in enum_type)
        raise ValidationError(f"{name} must be one of {allowed}; got {value!r}") from exc


def validate_output_mode(value: OutputMode | int) -> OutputMode:
    return validate_enum(OutputMode, value, "output mode")  # type: ignore[return-value]


def validate_capture_rate(value: CaptureRate | int) -> CaptureRate:
    return validate_enum(CaptureRate, value, "capture rate")  # type: ignore[return-value]


def validate_current_range(value: CurrentRange | int) -> CurrentRange:
    return validate_enum(CurrentRange, value, "current range")  # type: ignore[return-value]


def validate_fault_mode(value: FaultSimulationMode | int) -> FaultSimulationMode:
    return validate_enum(FaultSimulationMode, value, "fault simulation mode")  # type: ignore[return-value]


def validate_language(value: Language | int) -> Language:
    return validate_enum(Language, value, "language")  # type: ignore[return-value]


def validate_lan_connection_type(value: LanConnectionType | int) -> LanConnectionType:
    return validate_enum(LanConnectionType, value, "LAN connection type")  # type: ignore[return-value]


def validate_serial_baudrate(baudrate: int) -> int:
    if baudrate not in SERIAL_BAUDRATES:
        raise ValidationError(f"Baudrate must be one of {sorted(SERIAL_BAUDRATES)}; got {baudrate!r}")
    return baudrate


def validate_ip_address(ip: str) -> str:
    try:
        ipaddress.ip_address(ip)
    except ValueError as exc:
        raise ValidationError(f"Invalid IPv4/IPv6 address: {ip!r}") from exc
    return ip


def enforce_limit(name: str, value: float, minimum: float | None, maximum: float | None) -> None:
    if minimum is not None and value < minimum:
        raise SafetyError(f"{name}={value} below configured minimum {minimum}")
    if maximum is not None and value > maximum:
        raise SafetyError(f"{name}={value} above configured maximum {maximum}")


def enforce_channel_limit(kind: str, value: float, limits: ChannelLimits) -> None:
    match kind:
        case "voltage_v":
            enforce_limit(kind, value, limits.min_voltage_v, limits.max_voltage_v)
        case "current_ma":
            enforce_limit(kind, value, limits.min_current_ma, limits.max_current_ma)
        case "resistance_mohm":
            enforce_limit(kind, value, limits.min_resistance_mohm, limits.max_resistance_mohm)
        case "power_mw":
            enforce_limit(kind, value, limits.min_power_mw, limits.max_power_mw)
        case "runtime_s":
            enforce_limit(kind, value, limits.min_runtime_s, limits.max_runtime_s)
        case "capacity_mah":
            enforce_limit(kind, value, limits.min_capacity_mah, limits.max_capacity_mah)
        case _:
            raise ValidationError(f"Unknown limit kind: {kind}")
