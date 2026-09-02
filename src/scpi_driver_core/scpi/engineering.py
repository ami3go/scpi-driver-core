"""Parsing of human-friendly engineering values such as ``500mA`` or ``2.2k``.

This exists for values a human types into a test procedure or configuration
file, not for instrument responses; a device answering ``MEAS:VOLT?`` is parsed
with :func:`~scpi_driver_core.scpi.parsers.parse_float`.

Case rules, stated explicitly because ``m`` and ``M`` differ by a factor of a
billion:

- Prefixes are case-sensitive: ``m`` is milli and ``M`` is mega. The single
  exception is ``k``/``K``, both kilo, since ``K`` is near-universal in practice
  and kelvin is not a supported unit.
- A single-character unit must match case exactly. ``12V`` is volts; ``12v`` is
  rejected. This is what keeps ``1f`` (femto, dimensionless) distinct from a
  farad, and ``1a`` from an ampere.
- Multi-character units are case-insensitive, since no prefix is longer than
  one character: ``hz``, ``Hz`` and ``HZ`` are all hertz.

Anything outside these rules is rejected rather than guessed at.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from scpi_driver_core.exceptions import ResponseParseError

__all__ = ["SI_PREFIXES", "SUPPORTED_UNITS", "EngineeringValue", "parse_engineering_value"]

_SI_PREFIX_VALUES: Final[dict[str, float]] = {
    "f": 1e-15,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,  # MICRO SIGN
    "μ": 1e-6,  # GREEK SMALL LETTER MU
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "G": 1e9,
    "T": 1e12,
}

SI_PREFIXES: Final[Mapping[str, float]] = MappingProxyType(_SI_PREFIX_VALUES)
"""Supported SI prefixes, exposed read-only so a consumer cannot mutate global
state. Centi, deci, deca and hecto are deliberately absent: they are vanishingly
rare in instrument work and ``c``/``d`` would collide with plausible future
units."""

_SINGLE_CHAR_UNITS: Final[dict[str, str]] = {
    "V": "V",
    "A": "A",
    "W": "W",
    "F": "F",
    "H": "H",
    "s": "s",
}

#: Keyed by the casefolded suffix. Both the OHM SIGN (U+2126) and GREEK CAPITAL
#: OMEGA (U+03A9) casefold to GREEK SMALL OMEGA, so one entry covers both.
_MULTI_CHAR_UNITS: Final[dict[str, str]] = {
    "hz": "Hz",
    "ohm": "Ohm",
    "ohms": "Ohm",
    "\u03c9": "Ohm",
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
"""Canonical units this module can produce.

Derived from the lookup tables rather than written out, so it cannot drift out
of sync when a unit is added."""

_NUMBER = re.compile(
    r"""^\s*
        (?P<number>[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)
        \s*
        (?P<suffix>.*?)
        \s*$""",
    re.VERBOSE | re.DOTALL,
)


@dataclass(frozen=True)
class EngineeringValue:
    """A parsed engineering value, normalized to its base SI unit.

    ``500mA`` yields ``value=0.5`` and ``unit="A"``. A value with no unit, such
    as ``2.2k``, yields ``unit=""`` and is dimensionless.
    """

    value: float
    unit: str
    raw: str


def _resolve_unit(suffix: str) -> str | None:
    """Return the canonical unit for ``suffix``, or ``None`` if unrecognized."""
    if not suffix:
        return ""
    if len(suffix) == 1:
        single = _SINGLE_CHAR_UNITS.get(suffix)
        if single is not None:
            return single
        return _MULTI_CHAR_UNITS.get(suffix.casefold())
    return _MULTI_CHAR_UNITS.get(suffix.casefold())


def parse_engineering_value(text: str, *, expected_unit: str | None = None) -> EngineeringValue:
    """Parse ``text`` into a value scaled to its base SI unit.

    Args:
        text: for example ``12V``, ``500 mA``, ``10uA``, ``2.2k`` or ``500ms``.
        expected_unit: if given, the parsed unit must match it. A dimensionless
            value is accepted against any expectation, so ``2.2k`` still works
            where ohms are wanted.

    Raises:
        ResponseParseError: if there is no number, the number is non-finite, the
            suffix is not a recognized prefix/unit combination, or the unit
            contradicts ``expected_unit``.
    """
    match = _NUMBER.match(text)
    if match is None:
        raise ResponseParseError(f"expected an engineering value, got {text!r}", raw=text)

    # The pattern only matches digit sequences, so float() cannot fail here.
    # It can still overflow to infinity, as "1e999" does.
    magnitude = float(match.group("number"))
    if not math.isfinite(magnitude):
        raise ResponseParseError(f"value overflows to infinity: {text!r}", raw=text)

    suffix = match.group("suffix")
    scale = 1.0

    unit = _resolve_unit(suffix)
    if unit is None:
        prefix_scale = SI_PREFIXES.get(suffix[0])
        if prefix_scale is None:
            raise ResponseParseError(f"unknown unit {suffix!r} in {text!r}", raw=text)
        unit = _resolve_unit(suffix[1:])
        if unit is None:
            raise ResponseParseError(f"unknown unit {suffix[1:]!r} in {text!r}", raw=text)
        scale = prefix_scale

    if expected_unit is not None and unit and unit.casefold() != expected_unit.casefold():
        raise ResponseParseError(
            f"expected unit {expected_unit!r}, got {unit!r} in {text!r}", raw=text
        )

    return EngineeringValue(value=magnitude * scale, unit=unit, raw=text)
