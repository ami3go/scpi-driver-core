"""Enums for Agilent 33220A SCPI argument values, grounded in the User's Guide (9018-04437).

Real SCPI accepts both a command's long form and its abbreviated mnemonic
(e.g. "SINusoid" or "SIN") — SCPI's own rule is that the short (canonical)
form is always a *prefix* of the long form, which is exactly what the
manual's own mixed-case notation marks. Every enum here stores the short
form as its canonical value (what's actually sent on the wire) but accepts
the long form too, case-insensitively, via a single generic prefix-matching
``_missing_`` hook — no per-enum alias table needed.
"""

from __future__ import annotations

from enum import Enum


class _ScpiEnum(str, Enum):
    """Base class: accepts a value's long SCPI form as well as its canonical short mnemonic."""

    @classmethod
    def _missing_(cls, value: object) -> _ScpiEnum | None:
        if not isinstance(value, str):
            return None
        token = value.strip().upper()
        for member in cls:
            if member.value.upper() == token:
                return member
        for member in cls:
            if token.startswith(member.value.upper()):
                return member
        return None


class Function(_ScpiEnum):
    """FUNCtion {SINusoid|SQUare|RAMP|PULSe|NOISe|DC|USER}."""

    SINE = "SIN"
    SQUARE = "SQU"
    RAMP = "RAMP"
    PULSE = "PULS"
    NOISE = "NOIS"
    DC = "DC"
    USER = "USER"


class ModulatingShape(_ScpiEnum):
    """<mod>:INTernal:FUNCtion {SINusoid|SQUare|RAMP|NRAMp|TRIangle|NOISe|USER}.

    Shared by AM/FM/PM/PWM's internal modulating-waveform selector — a
    different, wider set than :class:`Function` (adds NRAMp/TRIangle, drops
    PULSe/DC).
    """

    SINE = "SIN"
    SQUARE = "SQU"
    RAMP = "RAMP"
    NEGATIVE_RAMP = "NRAMP"
    TRIANGLE = "TRI"
    NOISE = "NOIS"
    USER = "USER"


class AmplitudeUnit(_ScpiEnum):
    """VOLTage:UNIT {VPP|VRMS|DBM}."""

    VPP = "VPP"
    VRMS = "VRMS"
    DBM = "DBM"


class OutputPolarity(_ScpiEnum):
    """OUTPut:POLarity {NORMal|INVerted}."""

    NORMAL = "NORM"
    INVERTED = "INV"


class TriggerSource(_ScpiEnum):
    """TRIGger:SOURce {IMMediate|EXTernal|BUS}."""

    IMMEDIATE = "IMM"
    EXTERNAL = "EXT"
    BUS = "BUS"


class TriggerSlope(_ScpiEnum):
    """TRIGger:SLOpe {POSitive|NEGative}."""

    POSITIVE = "POS"
    NEGATIVE = "NEG"


class BurstMode(_ScpiEnum):
    """BURSt:MODE {TRIGgered|GATed}."""

    TRIGGERED = "TRIG"
    GATED = "GAT"


class GatePolarity(_ScpiEnum):
    """BURSt:GATE:POLarity {NORMal|INVerted}."""

    NORMAL = "NORM"
    INVERTED = "INV"


class SweepSpacing(_ScpiEnum):
    """SWEep:SPACing {LINear|LOGarithmic}."""

    LINEAR = "LIN"
    LOGARITHMIC = "LOG"


class ModulationSource(_ScpiEnum):
    """<mod>:SOURce {INTernal|EXTernal}."""

    INTERNAL = "INT"
    EXTERNAL = "EXT"


class FrontPanelLockExclude(_ScpiEnum):
    """SYSTem:KLOCk:EXCLude {NONE|LOCal}."""

    NONE = "NONE"
    LOCAL = "LOC"


class AngleUnit(_ScpiEnum):
    """UNIT:ANGLe {DEGree|RADian}."""

    DEGREE = "DEG"
    RADIAN = "RAD"
