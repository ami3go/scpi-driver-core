"""Parsing of human-friendly engineering values such as ``500mA`` or ``2.2k``.

Prefixes are case-sensitive: ``m`` is milli and ``M`` is mega; ``k`` and ``K``
are both accepted for kilo. Multi-character units remain case-insensitive, so
``mHz`` and ``mhz`` both denote millihertz. The parser does not guess that a
lowercase prefix was intended to be uppercase; applications wanting stricter
human-entry conventions should validate their configuration before parsing.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final

from scpi_driver_core.exceptions import ResponseParseError

__all__ = ["SI_PREFIXES", "SUPPORTED_UNITS", "EngineeringValue", "parse_engineering_value"]

_PREFIX_EXPONENT: Final[dict[str, int]] = {
    "f": -15,
    "p": -12,
    "n": -9,
    "u": -6,
    "µ": -6,
    "μ": -6,
    "m": -3,
    "k": 3,
    "K": 3,
    "M": 6,
    "G": 9,
    "T": 12,
}
SI_PREFIXES: Final[Mapping[str, float]] = MappingProxyType(
    {prefix: float(Decimal(1).scaleb(exponent)) for prefix, exponent in _PREFIX_EXPONENT.items()}
)

_SINGLE_CHAR_UNITS: Final[dict[str, str]] = {
    "V": "V",
    "A": "A",
    "W": "W",
    "F": "F",
    "H": "H",
    "s": "s",
}
_MULTI_CHAR_UNITS: Final[dict[str, str]] = {
    "hz": "Hz",
    "ohm": "Ohm",
    "ohms": "Ohm",
    "ω": "Ohm",
    "sec": "s",
    "secs": "s",
    "amp": "A",
    "amps": "A",
    "volt": "V",
    "volts": "V",
    "watt": "W",
    "watts": "W",
}
SUPPORTED_UNITS: Final[frozenset[str]] = frozenset(_SINGLE_CHAR_UNITS.values()) | frozenset(
    _MULTI_CHAR_UNITS.values()
)
_NUMBER = re.compile(
    r"^\s*(?P<number>[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)\s*(?P<suffix>.*?)\s*$",
    re.DOTALL,
)


@dataclass(frozen=True)
class EngineeringValue:
    value: float
    unit: str
    raw: str


def _resolve_unit(suffix: str) -> str | None:
    if not suffix:
        return ""
    if len(suffix) == 1:
        single = _SINGLE_CHAR_UNITS.get(suffix)
        if single is not None:
            return single
        return _MULTI_CHAR_UNITS.get(suffix.casefold())
    return _MULTI_CHAR_UNITS.get(suffix.casefold())


def parse_engineering_value(text: str, *, expected_unit: str | None = None) -> EngineeringValue:
    """Parse a human engineering value with exact decimal prefix scaling."""
    match = _NUMBER.match(text)
    if match is None:
        raise ResponseParseError(f"expected an engineering value, got {text!r}", raw=text)
    try:
        magnitude = Decimal(match.group("number"))
    except InvalidOperation as exc:
        raise ResponseParseError(f"expected an engineering value, got {text!r}", raw=text) from exc

    suffix = match.group("suffix")
    exponent = 0
    unit = _resolve_unit(suffix)
    if unit is None:
        if not suffix:
            raise ResponseParseError(f"unknown unit in {text!r}", raw=text)
        prefix = suffix[0]
        if prefix not in _PREFIX_EXPONENT:
            raise ResponseParseError(f"unknown unit {suffix!r} in {text!r}", raw=text)
        exponent = _PREFIX_EXPONENT[prefix]
        unit = _resolve_unit(suffix[1:])
        if unit is None:
            raise ResponseParseError(f"unknown unit {suffix[1:]!r} in {text!r}", raw=text)

    scaled = magnitude.scaleb(exponent)
    value = float(scaled)
    if not math.isfinite(value):
        raise ResponseParseError(f"value overflows to infinity: {text!r}", raw=text)
    if expected_unit is not None and unit and unit.casefold() != expected_unit.casefold():
        raise ResponseParseError(
            f"expected unit {expected_unit!r}, got {unit!r} in {text!r}", raw=text
        )
    return EngineeringValue(value=value, unit=unit, raw=text)
