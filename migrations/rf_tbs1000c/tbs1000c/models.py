"""Typed result models returned by the TBS1000C core driver."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class InstrumentIdentity:
    """Parsed *IDN? response.

    Manual format: ``TEKTRONIX,<model>,CF:91.1CT FV:v<fw> TBS 1XXXC:v<module fw>``.
    """

    manufacturer: str
    model: str
    serial: str
    firmware: str
    raw: str


@dataclass(frozen=True)
class WaveformPreamble:
    """Decoded WFMOutpre? fields. Every field mandatory for scaling raw CURVe? bytes."""

    bit_nr: int
    bn_fmt: str
    byt_nr: int
    encdg: str
    nr_pt: int
    record_length: int
    wfid: str
    x_increment: float
    x_zero: float
    x_unit: str
    y_multiplier: float
    y_offset: float
    y_zero: float
    y_unit: str


@dataclass(frozen=True)
class Waveform:
    """A decoded waveform record: real (time, volts) pairs plus the preamble that produced them."""

    time_s: list[float]
    volts: list[float]
    preamble: WaveformPreamble


@dataclass(frozen=True)
class ChannelSettings:
    """Current per-channel vertical configuration, as reported by the instrument."""

    channel: int
    scale: float
    position: float
    offset: float
    coupling: str
    bandwidth_limit: str
    probe_gain: float
    label: str


@dataclass(frozen=True)
class TriggerSettings:
    """Current A-trigger (edge) configuration, as reported by the instrument."""

    source: str
    slope: str
    coupling: str
    level: float


@dataclass(frozen=True)
class CalibrationStatus:
    """CALibrate:INTERNal:STATus? / CALibrate:RESults?."""

    running: bool
    results: str = ""


@dataclass(frozen=True)
class ConnectionState:
    """RFDS-002 Section 12.1 normalized connection-state dictionary, as a typed object.

    ``as_dict()`` produces the exact Robot-facing shape.
    """

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


@dataclass
class ChannelNameProfile:
    """§5.3 config profile fragment: optional default channel labels applied after Connect."""

    labels: dict[str, str | None] = field(default_factory=dict)
