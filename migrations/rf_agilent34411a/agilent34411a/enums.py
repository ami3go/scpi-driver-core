"""Enums for Agilent 34411A SCPI argument values, grounded in the User's Guide
(34410-90001) and the Agilent 34410A/11A Command Quick Reference.

Real SCPI accepts both a command's long form and its abbreviated mnemonic
(e.g. "IMMediate" or "IMM") — SCPI's own rule is that the short (canonical)
form is always a *prefix* of the long form. Every enum here stores the short
form as its canonical value (what's actually sent on the wire) but accepts
the long form too, case-insensitively, via the same generic prefix-matching
``_missing_`` hook already proven in ``agilent33220a.enums`` — reused
verbatim rather than re-derived.
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
    """FUNCtion "<function>" — the quoted-string function-name vocabulary.

    Unlike most SCPI mnemonics on this instrument, function names are sent
    as quoted strings (e.g. ``FUNCtion "VOLT:AC"``); the driver adds the
    quoting, this enum only carries the bare token.
    """

    DC_VOLTAGE = "VOLT"
    AC_VOLTAGE = "VOLT:AC"
    DC_CURRENT = "CURR"
    AC_CURRENT = "CURR:AC"
    RESISTANCE_2W = "RES"
    RESISTANCE_4W = "FRES"
    FREQUENCY = "FREQ"
    PERIOD = "PER"
    CAPACITANCE = "CAP"
    TEMPERATURE = "TEMP"
    CONTINUITY = "CONT"
    DIODE = "DIOD"


class AcFilter(_ScpiEnum):
    """<func>:BANDwidth {3|20|200} — the ac low-frequency filter bandwidth, in Hz.

    Values are the literal numeric bandwidth (Hz), matching what the
    instrument's own SCPI syntax uses in place of a mnemonic.
    """

    SLOW = "3"
    MEDIUM = "20"
    FAST = "200"


class TriggerSource(_ScpiEnum):
    """TRIGger:SOURce {IMMediate|EXTernal|BUS|INTernal}.

    ``INTernal`` (level triggering) is 34411A/L4411A-only and restricted to
    ac/dc voltage, ac/dc current, and 2-/4-wire resistance (task §9).
    """

    IMMEDIATE = "IMM"
    EXTERNAL = "EXT"
    BUS = "BUS"
    INTERNAL = "INT"


class TriggerSlope(_ScpiEnum):
    """TRIGger:SLOPe {POSitive|NEGative}."""

    POSITIVE = "POS"
    NEGATIVE = "NEG"


class SampleSource(_ScpiEnum):
    """SAMPle:SOURce {AUTO|TIMer}."""

    AUTO = "AUTO"
    TIMER = "TIM"


class AutoZeroMode(_ScpiEnum):
    """[SENSe:]<func>:ZERO:AUTO {OFF|ONCE|ON} — a genuine 3-state mode, not a bool."""

    OFF = "OFF"
    ONCE = "ONCE"
    ON = "ON"


class TemperatureProbeType(_ScpiEnum):
    """[SENSe:]TEMPerature:TRANsducer:TYPE {FRTD|RTD|THERmistor}."""

    RTD_4W = "FRTD"
    RTD_2W = "RTD"
    THERMISTOR = "THER"


class ThermistorType(_ScpiEnum):
    """[SENSe:]TEMPerature:TRANsducer:THERmistor:TYPE {2252|5000|10000} (ohms)."""

    OHMS_2252 = "2252"
    OHMS_5000 = "5000"
    OHMS_10000 = "10000"


class TemperatureUnit(_ScpiEnum):
    """UNIT:TEMPerature {C|F|K}."""

    CELSIUS = "C"
    FAHRENHEIT = "F"
    KELVIN = "K"


class MathFunction(_ScpiEnum):
    """CALCulate:FUNCtion {DB|DBM|AVERage|LIMit}.

    Deliberately excludes ``NULL``: the manual documents that value as
    deprecated 34401A-compatibility-only (task §6 item 4) — this driver
    must always use the per-function ``[SENSe:]<function>:NULL`` path
    instead, never ``CALCulate:FUNCtion NULL``. Omitting it from this enum
    makes sending it a type error, not just a documentation note.
    """

    DB = "DB"
    DBM = "DBM"
    STATISTICS = "AVER"
    LIMIT = "LIM"
