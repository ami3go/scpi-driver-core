"""Typed result models returned by the Agilent 34411A core driver."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentIdentity:
    """Parsed *IDN? response: ``<manufacturer>,<model>,<serial>,<firmware>``."""

    manufacturer: str
    model: str
    serial: str
    firmware: str
    raw: str


@dataclass(frozen=True)
class MeasurementSettings:
    """Current configuration snapshot for the active measurement function.

    Not every field is meaningful for every function (task §8) — e.g.
    capacitance has no integration-time fields, continuity/diode have none
    at all. Fields that don't apply to the active function are ``None``.
    """

    function: str
    range_value: float | None
    auto_range: bool | None
    nplc: float | None
    aperture_s: float | None
    auto_zero: str | None
    offset_compensation: bool | None
    ac_filter_bandwidth_hz: float | None
    input_impedance_auto: bool | None
    null_enabled: bool
    null_value: float


@dataclass(frozen=True)
class TriggerSettings:
    """Current trigger/sample subsystem configuration."""

    source: str
    level: float
    slope: str
    delay_s: float
    delay_auto: bool
    trigger_count: float
    sample_count: float
    sample_source: str
    sample_timer_s: float
    pretrigger_sample_count: float


@dataclass(frozen=True)
class StatisticsResult:
    """CALCulate:AVERage:* readback."""

    average: float
    minimum: float
    maximum: float
    std_deviation: float
    peak_to_peak: float
    count: int


@dataclass(frozen=True)
class ConnectionState:
    """RFDS-002 Section 12.1 normalized connection-state dictionary, as a typed object."""

    alias: str
    resource: str | None
    connected: bool
    communication_ok: bool
    transport: str | None
    identity: str | None
    timeout_s: float | None
    state: str

    def as_dict(self) -> dict[str, object]:
        return {
            "alias": self.alias,
            "resource": self.resource,
            "connected": self.connected,
            "communication_ok": self.communication_ok,
            "transport": self.transport,
            "identity": self.identity,
            "timeout_s": self.timeout_s,
            "state": self.state,
        }
