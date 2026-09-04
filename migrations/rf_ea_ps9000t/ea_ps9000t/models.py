"""Typed result models returned by the EA-PS 9000 T core driver."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstrumentIdentity:
    """Parsed *IDN? response.

    Unlike the 4-field *IDN? this repository's other drivers parse, this
    family returns 5 comma-separated fields: manufacturer, model, serial,
    firmware version(s), and an optional user-definable text (task §6
    item 6). ``user_text`` is an empty string, never None, when absent.
    """

    manufacturer: str
    model: str
    serial: str
    firmware: str
    user_text: str
    raw: str


@dataclass(frozen=True)
class NominalRatings:
    """SYSTem:NOMinal:* readback — the connected unit's actual rated values."""

    voltage: float
    current: float
    power: float


@dataclass(frozen=True)
class MeasuredValues:
    """MEASure:ARRay? readback."""

    voltage: float
    current: float
    power: float


@dataclass(frozen=True)
class ProtectionThresholds:
    """Overvoltage/overcurrent/overpower protection threshold readback."""

    overvoltage: float
    overcurrent: float
    overpower: float


@dataclass(frozen=True)
class AdjustmentLimits:
    """Adjustment-limit ("Limits") readback.

    Asymmetric by design (task §2/§9): there is no power low-limit command
    on this instrument family, so ``power_high`` has no ``power_low``
    counterpart — this is not an omission.
    """

    voltage_low: float
    voltage_high: float
    current_low: float
    current_high: float
    power_high: float


@dataclass(frozen=True)
class AlarmCounters:
    """SYSTem:ALARm:COUNt:* readback (PST-applicable subset only, task §2)."""

    overvoltage: int
    overtemperature: int
    overpower: int
    overcurrent: int
    power_fail: int


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
