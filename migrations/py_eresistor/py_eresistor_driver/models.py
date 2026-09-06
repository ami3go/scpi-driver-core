"""Dataclasses and enums used by the E-Resistor driver."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Optional


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    LOST = "LOST"
    CLOSED = "CLOSED"


class ConnectionLossPolicy(str, Enum):
    MARK_LOST_AND_ALARM = "mark_lost_and_alarm"
    ATTEMPT_ALL_OFF = "attempt_all_off"
    ATTEMPT_SAFE_RESISTANCE = "attempt_safe_resistance"
    IGNORE = "ignore"


class ReconnectStatePolicy(str, Enum):
    VERIFY_AND_HOLD = "verify_and_hold"
    RESTORE_LAST = "restore_last"
    ALL_OFF = "all_off"
    LEAVE_AS_IS = "leave_as_is"


class ShutdownPolicy(str, Enum):
    ALL_OFF = "all_off"
    LEAVE_AS_IS = "leave_as_is"
    RESTORE_SNAPSHOT = "restore_snapshot"


@dataclass(frozen=True)
class BoardInfo:
    """Information returned by network discovery.

    The canonical connection address is stored as ``host``. Convenience aliases are
    provided for user-facing code, so both ``board.host`` and ``board.ip`` work.
    Firmware can be accessed through ``board.firmware_version``, ``board.fw``,
    ``board.firmware``, or ``board.version``.
    """

    host: str
    serial: str | None = None
    firmware_version: str | None = None
    idn: str | None = None
    http_ok: bool = False
    scpi_ok: bool = False

    @property
    def ip(self) -> str:
        """IPv4 address / host name of the discovered board."""
        return self.host

    @property
    def address(self) -> str:
        """Alias for ``host`` / ``ip``."""
        return self.host

    @property
    def fw(self) -> str | None:
        """Short alias for firmware version."""
        return self.firmware_version

    @property
    def firmware(self) -> str | None:
        """Alias for firmware version."""
        return self.firmware_version

    @property
    def version(self) -> str | None:
        """Alias for firmware version."""
        return self.firmware_version

    @property
    def serial_number(self) -> str | None:
        """Alias for board serial number."""
        return self.serial

    @property
    def idn_parts(self) -> tuple[str, ...]:
        """Return the comma-separated ``*IDN?`` fields."""
        if not self.idn:
            return ()
        return tuple(part.strip() for part in self.idn.split(","))

    @property
    def manufacturer(self) -> str | None:
        """Manufacturer/vendor field from ``*IDN?`` when available."""
        parts = self.idn_parts
        return parts[0] if len(parts) >= 1 and parts[0] else None

    @property
    def vendor(self) -> str | None:
        """Alias for ``manufacturer``."""
        return self.manufacturer

    @property
    def model(self) -> str | None:
        """Model/product field from ``*IDN?`` when available."""
        parts = self.idn_parts
        return parts[1] if len(parts) >= 2 and parts[1] else None

    @property
    def product(self) -> str | None:
        """Alias for ``model``."""
        return self.model

    @property
    def scpi_address(self) -> str:
        """Default SCPI address string for display or logging."""
        return f"{self.host}:5025"

    @property
    def http_url(self) -> str:
        """Default HTTP URL for display or browser access."""
        return f"http://{self.host}/"

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary with canonical names and convenience aliases."""
        return {
            "host": self.host,
            "ip": self.ip,
            "address": self.address,
            "serial": self.serial,
            "serial_number": self.serial_number,
            "firmware_version": self.firmware_version,
            "fw": self.fw,
            "firmware": self.firmware,
            "version": self.version,
            "idn": self.idn,
            "manufacturer": self.manufacturer,
            "vendor": self.vendor,
            "model": self.model,
            "product": self.product,
            "http_ok": self.http_ok,
            "scpi_ok": self.scpi_ok,
            "scpi_address": self.scpi_address,
            "http_url": self.http_url,
        }


@dataclass(frozen=True)
class BranchCalibration:
    bit_index: int
    mosfet_name: str
    resistance_ohm: float


@dataclass
class ChannelCalibration:
    channel: int
    branches: list[BranchCalibration]
    source: str = "unknown"

    def branch_by_bit(self) -> dict[int, BranchCalibration]:
        return {b.bit_index: b for b in self.branches}


@dataclass
class DeviceCalibration:
    channels: dict[int, ChannelCalibration]
    serial: str | None = None
    firmware_version: str | None = None
    downloaded_at: datetime | None = None
    source: str = "unknown"
    checksum: str | None = None

    def mark_downloaded_now(self) -> None:
        self.downloaded_at = datetime.now(timezone.utc)


@dataclass(frozen=True)
class OutputSnapshot:
    masks: dict[int, str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "driver"


@dataclass(frozen=True)
class SetResistanceResult:
    channel: int
    requested_ohm: float
    calculated_ohm: float
    error_ohm: float
    error_percent: float
    mask: str
    active_bits: list[int]


@dataclass(frozen=True)
class SetTemperatureResult:
    channel: int
    requested_temperature_c: float
    interpolated_resistance_ohm: float
    calculated_resistance_ohm: float
    resistance_error_ohm: float
    resistance_error_percent: float
    mask: str
    resistance_result: SetResistanceResult


@dataclass(frozen=True)
class SimulationLogEntry:
    timestamp: datetime
    elapsed_s: float
    channel: int
    requested_type: str
    requested_value: float
    requested_resistance_ohm: float
    calculated_resistance_ohm: float
    error_percent: float
    mask: str
    timing_error_s: float = 0.0


@dataclass
class SafetyConfig:
    min_resistance_ohm: float | None = 300.0
    max_resistance_ohm: float | None = 20_000_000.0
    max_active_bits: int | None = 16
    safe_resistance_ohm: float | None = None
    connection_loss_policy: ConnectionLossPolicy = ConnectionLossPolicy.MARK_LOST_AND_ALARM
    max_unattended_time_s: float | None = None
    watchdog_timeout_s: float = 60.0


@dataclass
class ReconnectConfig:
    max_attempts: int | None = None
    backoff_base_s: float = 1.0
    backoff_max_s: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    state_policy: ReconnectStatePolicy = ReconnectStatePolicy.VERIFY_AND_HOLD


@dataclass
class WatchdogConfig:
    enabled: bool = False
    keepalive_interval_s: float = 30.0
    keepalive_command: str = "SYST:STAT?"
    on_fail: str = "reconnect"


@dataclass
class LoggingConfig:
    level: str = "INFO"
    structured_log: bool = False
    audit_log_file: str | None = None


@dataclass
class CalibrationConfig:
    auto_download: bool = True
    local_cache_file: str | None = None
    refresh_on_connect: bool = False
    max_age_hours: float | None = 168.0
    validate_on_load: bool = True
    on_stale: str = "warn_and_continue"


@dataclass
class DeviceProfile:
    device_name: str | None = None
    host: str = "192.168.7.50"
    scpi_port: int = 5025
    http_port: int = 80
    serial: str | None = None
    default_timeout_s: float = 2.0
    min_firmware_version: str | None = None
    firmware_check_on_connect: bool = False
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)
    watchdog: WatchdogConfig = field(default_factory=WatchdogConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    temperature_tables: dict[str, str] = field(default_factory=dict)
    state_persistence_file: str | None = None
    shutdown_policy: ShutdownPolicy = ShutdownPolicy.ALL_OFF


@dataclass(frozen=True)
class MetricsSnapshot:
    counters: dict[str, int]
    timings: dict[str, list[float]]
