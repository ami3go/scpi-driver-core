"""Generic parsers for decoded SCPI response text."""

from __future__ import annotations

import csv
import io
import math
import re
from decimal import Decimal, InvalidOperation
from typing import Final

from scpi_driver_core.exceptions import ConfigurationError, IdentityError, ResponseParseError
from scpi_driver_core.models import Identity, ScpiError

__all__ = [
    "parse_bool",
    "parse_csv",
    "parse_csv_floats",
    "parse_float",
    "parse_identity",
    "parse_int",
    "parse_optional_unit_float",
    "parse_scpi_error",
    "quote_scpi_string",
]

_TRUE_TOKENS = frozenset({"1", "ON", "TRUE"})
_FALSE_TOKENS = frozenset({"0", "OFF", "FALSE"})
_SCPI_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", re.ASCII)
_VALUE_WITH_UNIT = re.compile(
    r"^\s*(?P<number>[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[+-]?(?:inf(?:inity)?|nan))\s*(?P<unit>[^\W\d_]*)\s*$",
    re.IGNORECASE,
)

_SCPI_POS_INF: Final = Decimal("9.9E37")
_SCPI_NEG_INF: Final = Decimal("-9.9E37")
_SCPI_NAN: Final = Decimal("9.91E37")


def _decimal(text: str, response: str) -> Decimal:
    if _SCPI_DECIMAL.fullmatch(text) is None:
        raise ResponseParseError(f"expected a numeric SCPI value, got {response!r}", raw=response)
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # defensive after regex validation
        raise ResponseParseError(
            f"expected a numeric SCPI value, got {response!r}", raw=response
        ) from exc


def parse_float(
    response: str,
    *,
    allow_non_finite: bool = False,
    scpi_special_values: bool = True,
) -> float:
    """Parse an ASCII SCPI decimal value.

    SCPI-99 overload/special encodings ``9.9E37``, ``-9.9E37`` and ``9.91E37``
    are treated as +infinity, -infinity and NaN by default. Thus they are
    rejected when ``allow_non_finite`` is false rather than silently entering
    limit arithmetic as very large finite measurements.
    """
    text = response.strip()
    upper = text.upper()
    mnemonic: float | None = None
    if upper in {"INF", "+INF", "INFINITY", "+INFINITY"}:
        mnemonic = math.inf
    elif upper in {"-INF", "-INFINITY", "NINF"}:
        mnemonic = -math.inf
    elif upper in {"NAN", "+NAN", "-NAN"}:
        mnemonic = math.nan

    if mnemonic is not None:
        value = mnemonic
    else:
        exact = _decimal(text, response)
        if scpi_special_values and exact == _SCPI_NAN:
            value = math.nan
        elif scpi_special_values and exact == _SCPI_POS_INF:
            value = math.inf
        elif scpi_special_values and exact == _SCPI_NEG_INF:
            value = -math.inf
        else:
            value = float(exact)

    if not allow_non_finite and not math.isfinite(value):
        raise ResponseParseError(f"expected a finite float, got {response!r}", raw=response)
    return value


def parse_int(response: str) -> int:
    """Parse an integral ASCII SCPI decimal without binary-float precision loss.

    Decimal arithmetic avoids the previous loss of precision above ``2**53``.
    Values whose magnitude cannot be represented as a finite IEEE-754 double
    are still rejected, preserving the historical bounded numeric domain and
    preventing inputs such as ``1e999`` from turning into enormous Python
    integers unexpectedly.
    """
    text = response.strip()
    value = _decimal(text, response)
    if not math.isfinite(float(value)):
        raise ResponseParseError(f"expected a finite integer, got {response!r}", raw=response)
    integral = value.to_integral_value()
    if value != integral:
        raise ResponseParseError(f"expected an integer, got {response!r}", raw=response)
    return int(integral)


def parse_bool(response: str) -> bool:
    """Parse the conventional SCPI boolean forms, rejecting other numerics."""
    token = response.strip().upper()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    try:
        value = _decimal(response.strip(), response)
    except ResponseParseError as exc:
        raise ResponseParseError(f"expected a boolean, got {response!r}", raw=response) from exc
    if value == 0:
        return False
    if value == 1:
        return True
    raise ResponseParseError(f"expected a boolean, got {response!r}", raw=response)


def parse_csv(response: str) -> list[str]:
    """Split a comma-separated response, honoring quoted fields."""
    if not response.strip():
        return []
    try:
        rows = list(csv.reader(io.StringIO(response), skipinitialspace=True))
    except csv.Error as exc:
        raise ResponseParseError(f"malformed CSV response {response!r}", raw=response) from exc
    return [field for row in rows for field in row]


def parse_csv_floats(
    response: str,
    *,
    allow_non_finite: bool = False,
    scpi_special_values: bool = True,
) -> list[float]:
    return [
        parse_float(
            field,
            allow_non_finite=allow_non_finite,
            scpi_special_values=scpi_special_values,
        )
        for field in parse_csv(response)
    ]


def parse_optional_unit_float(
    response: str,
    *,
    expected_unit: str | None = None,
    allow_non_finite: bool = False,
    scpi_special_values: bool = True,
) -> float:
    match = _VALUE_WITH_UNIT.match(response)
    if match is None:
        raise ResponseParseError(f"expected a number, got {response!r}", raw=response)
    value = parse_float(
        match.group("number"),
        allow_non_finite=allow_non_finite,
        scpi_special_values=scpi_special_values,
    )
    unit = match.group("unit")
    if expected_unit is not None and unit and unit.casefold() != expected_unit.casefold():
        raise ResponseParseError(
            f"expected unit {expected_unit!r}, got {unit!r} in {response!r}", raw=response
        )
    return value


def parse_identity(response: str) -> Identity:
    try:
        fields = parse_csv(response)
    except ResponseParseError as exc:
        raise IdentityError(f"malformed *IDN? reply {response!r}") from exc
    trimmed = [field.strip() for field in fields]
    if len(trimmed) < 2 or not trimmed[0] or not trimmed[1]:
        raise IdentityError(f"*IDN? reply lacks manufacturer and model: {response!r}")

    def optional(index: int) -> str | None:
        return None if index >= len(trimmed) or not trimmed[index] else trimmed[index]

    return Identity(
        manufacturer=trimmed[0],
        model=trimmed[1],
        serial_number=optional(2),
        firmware_version=optional(3),
        raw=response,
    )


def parse_scpi_error(response: str) -> ScpiError:
    fields = parse_csv(response)
    if len(fields) < 2:
        raise ResponseParseError(f"expected a code and message, got {response!r}", raw=response)
    try:
        code = parse_int(fields[0].strip())
    except ResponseParseError as exc:
        raise ResponseParseError(
            f"expected a numeric error code, got {response!r}", raw=response
        ) from exc
    return ScpiError(code=code, message=",".join(fields[1:]).strip(), raw=response)


def quote_scpi_string(value: str) -> str:
    """Quote SCPI string data without permitting line-oriented command injection."""
    if "\r" in value or "\n" in value:
        raise ConfigurationError("SCPI string data must not contain CR or LF")
    return '"' + value.replace('"', '""') + '"'
