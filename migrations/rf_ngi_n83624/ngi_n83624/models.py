"""Typed models, enums, and configuration dataclasses for NGI N83624."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from time import monotonic
from typing import Protocol


class OutputMode(IntEnum):
    """N83624 channel operating mode."""

    SOURCE = 0
    CHARGE = 1
    SOC = 3
    SEQUENCE = 128


class OutputState(IntEnum):
    """Output ON/OFF value."""

    OFF = 0
    ON = 1


class CurrentRange(IntEnum):
    """Source-mode current readback/range selection."""

    HIGH = 0
    LOW = 2
    AUTO = 3


class CaptureRate(IntEnum):
    """Measurement capture/sampling rate."""

    FAST_10MS = 0
    MEDIUM_120MS = 1
    SLOW_480MS = 2


class FaultSimulationMode(IntEnum):
    """Optional fault simulation relay modes."""

    NORMAL = 0
    OPEN_POSITIVE = 1
    OPEN_NEGATIVE = 4
    OUTPUT_SHORTED = 8
    REVERSE_POLARITY = 96


class LanConnectionType(IntEnum):
    """LAN command connection mode stored in the instrument."""

    UDP = 0
    TCP = 1


class Language(IntEnum):
    """Instrument HMI language."""

    CHINESE = 0
    ENGLISH = 1


class SessionState(Enum):
    """High-level driver session state."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED_UNVERIFIED = "connected_unverified"
    READY = "ready"
    FAULTED = "faulted"
    RECOVERING = "recovering"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True)
class Measurement:
    """Measurements returned by :meth:`N83624Channel.measure_all`.

    Field semantics: a field is ``None`` only when that quantity was not requested,
    not implemented by the current command path, or explicitly unavailable due to a
    verified protocol limitation. Communication failures raise exceptions instead of
    returning ``None``.
    """

    channel: int
    voltage_v: float | None = None
    current_ma: float | None = None
    power_w: float | None = None
    capacity_mah: float | None = None
    resistance_mohm: float | None = None


@dataclass(frozen=True)
class ChannelStatus:
    """Decoded output status/event bitfield."""

    raw: int
    output_on: bool
    ovp: bool
    ocp: bool
    opp: bool
    otp: bool
    fault_relay_voltage_current_present: bool
    fault_relay_wrong_mode: bool
    readback_range: int | None

    @classmethod
    def from_raw(cls, raw: int) -> "ChannelStatus":
        readback_range = (raw >> 16) & 0b111
        return cls(
            raw=raw,
            output_on=bool(raw & (1 << 0)),
            ovp=bool(raw & (1 << 1)),
            ocp=bool(raw & (1 << 2)),
            opp=bool(raw & (1 << 3)),
            otp=bool(raw & (1 << 4)),
            fault_relay_voltage_current_present=bool(raw & (1 << 5)),
            fault_relay_wrong_mode=bool(raw & (1 << 6)),
            readback_range=readback_range if readback_range in (0, 1, 2) else None,
        )


@dataclass(frozen=True)
class SocStep:
    """One SOC table step."""

    capacity_mah: float
    voltage_v: float
    current_limit_ma: float
    resistance_mohm: float


@dataclass(frozen=True)
class SequenceStep:
    """One sequence table step."""

    voltage_v: float
    current_limit_ma: float
    resistance_mohm: float
    runtime_s: float
    link_start: int = -1
    link_end: int = -1
    link_cycle: int = 0


@dataclass(frozen=True)
class ChannelLimits:
    """Configurable per-channel software limits.

    The SCPI programming guide does not provide complete electrical ratings, so a
    production bench must provide verified model-specific limits before enabling
    outputs when ``DriverSafetyPolicy.require_limits_before_output_on`` is true.
    """

    min_voltage_v: float = 0.0
    max_voltage_v: float | None = None
    min_current_ma: float = 0.0
    max_current_ma: float | None = None
    min_resistance_mohm: float = 0.0
    max_resistance_mohm: float | None = None
    min_power_mw: float = 0.0
    max_power_mw: float | None = None
    min_runtime_s: float = 0.0
    max_runtime_s: float | None = None
    min_capacity_mah: float = 0.0
    max_capacity_mah: float | None = None

    def has_output_enable_limits(self) -> bool:
        """Return true when voltage and current max limits are explicitly configured."""
        return self.max_voltage_v is not None and self.max_current_ma is not None


@dataclass(frozen=True)
class InstrumentLimits:
    """Instrument-wide and per-channel limits.

    ``default_channel_limits`` apply to all channels unless an entry is provided in
    ``channel_limits``. This supports benches where some channels have different
    cable, DUT, relay, or board ratings.
    """

    model_name: str | None = None
    default_channel_limits: ChannelLimits = field(default_factory=ChannelLimits)
    channel_limits: dict[int, ChannelLimits] = field(default_factory=dict)

    def for_channel(self, channel: int) -> ChannelLimits:
        return self.channel_limits.get(channel, self.default_channel_limits)


@dataclass(frozen=True)
class DriverSafetyPolicy:
    """Safe-by-default behavior switches."""

    require_limits_before_output_on: bool = True
    output_off_on_close: bool = False
    output_off_on_exception: bool = True
    fault_simulation_enabled: bool = False
    require_interlock_for_output_on: bool = True
    require_interlock_for_fault_simulation: bool = True
    require_status_check_after_setters: bool = True
    require_identity_check_on_connect: bool = True
    require_state_resync_after_reconnect: bool = True
    dangerous_system_write_requires_confirmation: bool = True


@dataclass(frozen=True)
class HeartbeatConfig:
    """Heartbeat watchdog configuration."""

    interval_s: float = 10.0
    query: str = "*IDN?"
    fail_after: int = 3


@dataclass(frozen=True)
class ReconnectPolicy:
    """Reconnect configuration for session recovery."""

    enabled: bool = True
    max_attempts: int = 3
    delay_s: float = 1.0
    resync_after_reconnect: bool = True


@dataclass(frozen=True)
class RetryPolicy:
    """Communication retry policy.

    Retries apply only to queries considered idempotent by the driver. Setters and
    output/fault commands are not retried automatically unless explicitly coded as a
    safe compound operation.
    """

    retries: int = 0
    delay_s: float = 0.1
    retry_queries_only: bool = True


@dataclass(frozen=True)
class ChannelConfiguration:
    """Snapshot of user-visible channel configuration."""

    channel: int
    mode: OutputMode
    output_enabled: bool
    source_voltage_v: float | None = None
    source_current_limit_ma: float | None = None
    source_current_range: CurrentRange | None = None
    charge_voltage_v: float | None = None
    charge_current_limit_ma: float | None = None
    charge_resistance_mohm: float | None = None
    ocp_current_ma: float | None = None
    ovp_voltage_v: float | None = None
    opp_power_mw: float | None = None
    capture_rate: CaptureRate | None = None


class BenchInterlock(Protocol):
    """External bench safety interlock contract."""

    def assert_output_allowed(self, channel: int) -> None:
        """Raise InterlockError if output is not allowed."""

    def assert_fault_simulation_allowed(self, channel: int) -> None:
        """Raise InterlockError if fault relay operation is not allowed."""


class NullBenchInterlock:
    """Permissive interlock for development or explicitly non-production usage."""

    def assert_output_allowed(self, channel: int) -> None:  # noqa: ARG002
        return None

    def assert_fault_simulation_allowed(self, channel: int) -> None:  # noqa: ARG002
        return None


@dataclass(frozen=True)
class CommunicationObservation:
    """Observed communication health data for watchdogs and logs."""

    last_success_monotonic_s: float | None = None
    last_failure_monotonic_s: float | None = None
    consecutive_failures: int = 0
    last_error: str | None = None

    @classmethod
    def success(cls, previous: "CommunicationObservation | None" = None) -> "CommunicationObservation":
        return cls(
            last_success_monotonic_s=monotonic(),
            last_failure_monotonic_s=previous.last_failure_monotonic_s if previous else None,
            consecutive_failures=0,
            last_error=None,
        )

    @classmethod
    def failure(cls, error: BaseException, previous: "CommunicationObservation | None" = None) -> "CommunicationObservation":
        return cls(
            last_success_monotonic_s=previous.last_success_monotonic_s if previous else None,
            last_failure_monotonic_s=monotonic(),
            consecutive_failures=(previous.consecutive_failures + 1) if previous else 1,
            last_error=f"{type(error).__name__}: {error}",
        )
