"""Typed result models returned by the Agilent 33220A core driver."""

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
class OutputSettings:
    """Current output configuration, as reported by the instrument."""

    function: str
    frequency: float
    amplitude: float
    amplitude_unit: str
    offset: float
    output_enabled: bool
    output_load: str
    polarity: str


@dataclass(frozen=True)
class TriggerSettings:
    """Current sweep/burst trigger configuration."""

    source: str
    slope: str


@dataclass(frozen=True)
class ArbWaveformAttributes:
    """DATA:ATTRibute:* query results for one arbitrary waveform."""

    name: str
    average: float
    crest_factor: float
    points: int
    peak_to_peak: float


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
