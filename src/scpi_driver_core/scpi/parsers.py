"""Generic parsers for SCPI response text.

These operate on text already decoded by :class:`~scpi_driver_core.scpi.codec.ScpiTextCodec`,
so surrounding whitespace is padding an instrument added, not protocol framing,
and is tolerated. The prohibition on ``strip()`` applies to the framing layer,
which has already run by this point.

Every failure raises with the offending response attached, and nothing is ever
silently coerced: a value that cannot be parsed is an error, never a zero.
Device-specific sentinels, such as the 9.9E37 an overloaded meter returns,
stay in the concrete driver; to the core that is simply a large float.
"""

from __future__ import annotations

import csv
import io
import math
import re

from scpi_driver_core.exceptions import IdentityError, ResponseParseError
from scpi_driver_core.models import Identity, ScpiError

__all__ = [
    "parse_bool",
    "parse_csv",
    "parse_float",
    "parse_identity",
    "parse_int",
    "parse_optional_unit_float",
    "parse_scpi_error",
    "quote_scpi_string",
]

_TRUE_TOKENS = frozenset({"1", "ON", "TRUE"})
_FALSE_TOKENS = frozenset({"0", "OFF", "FALSE"})

#: A number, optionally followed by a unit suffix. The suffix is restricted to
#: letters, so trailing junk such as "1 2" is rejected rather than read as a
#: value with a nonsense unit. ``[^\W\d_]`` covers Ω and µ as well as ASCII.
_VALUE_WITH_UNIT = re.compile(
    r"""^\s*
        (?P<number>[+-]?(?:(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?|inf(?:inity)?|nan))
        \s*
        (?P<unit>[^\W\d_]*)
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def parse_float(response: str, *, allow_non_finite: bool = False) -> float:
    """Parse a floating-point response.

    Args:
        allow_non_finite: permit ``NaN`` and infinities. Off by default,
            because a device reporting one usually indicates a fault the caller
            should see rather than propagate into arithmetic.

    Raises:
        ResponseParseError: if the response is not a number, or is non-finite
            and ``allow_non_finite`` is false.
    """
    text = response.strip()
    try:
        value = float(text)
    except ValueError as exc:
        raise ResponseParseError(f"expected a float, got {response!r}", raw=response) from exc
    if not allow_non_finite and not math.isfinite(value):
        raise ResponseParseError(f"expected a finite float, got {response!r}", raw=response)
    return value


def parse_int(response: str) -> int:
    """Parse an integer response.

    Accepts the ``+1.00000000E+02`` form some instruments return where an
    integer is documented, but only when the value is exactly integral.

    Raises:
        ResponseParseError: if the response is not an integer.
    """
    text = response.strip()
    try:
        return int(text)
    except ValueError:
        pass

    try:
        value = float(text)
    except ValueError as exc:
        raise ResponseParseError(f"expected an integer, got {response!r}", raw=response) from exc

    if not math.isfinite(value) or value != int(value):
        raise ResponseParseError(f"expected an integer, got {response!r}", raw=response)
    return int(value)


def parse_bool(response: str) -> bool:
    """Parse a SCPI boolean.

    Accepts ``1``/``0``, ``ON``/``OFF`` and ``TRUE``/``FALSE`` in any case, and
    numeric forms such as ``1.000000E+00`` whose value is exactly 0 or 1.

    Raises:
        ResponseParseError: for anything else, including other numbers.
    """
    token = response.strip().upper()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False

    try:
        value = float(token)
    except ValueError as exc:
        raise ResponseParseError(f"expected a boolean, got {response!r}", raw=response) from exc
    if value == 0:
        return False
    if value == 1:
        return True
    raise ResponseParseError(f"expected a boolean, got {response!r}", raw=response)


def parse_csv(response: str) -> list[str]:
    """Split a comma-separated response, honoring quoted fields.

    Uses real CSV parsing rather than ``split(",")`` so a quoted field
    containing a comma survives. Fields are returned as they appear, apart from
    whitespace immediately after a separator; the typed parsers tolerate any
    remaining padding.

    An empty response yields an empty list. A response containing embedded
    newlines is flattened into one list of fields, since a SCPI reply is a
    single logical record however the instrument chose to wrap it.

    Raises:
        ResponseParseError: if the response is not parsable as CSV, which a
            stray carriage return will cause.
    """
    if not response.strip():
        return []
    try:
        rows = list(csv.reader(io.StringIO(response), skipinitialspace=True))
    except csv.Error as exc:
        raise ResponseParseError(f"malformed CSV response {response!r}", raw=response) from exc

    fields: list[str] = []
    for row in rows:
        fields.extend(row)
    return fields


def parse_optional_unit_float(
    response: str,
    *,
    expected_unit: str | None = None,
    allow_non_finite: bool = False,
) -> float:
    """Parse a number that may carry a unit suffix.

    Instruments in the source driver set answer the same query as either
    ``500.0`` or ``500.0 V``, sometimes depending on firmware, so both forms
    have to work. The unit is not scaled: this returns the number as written.
    For prefix handling such as ``500mV``, use
    :func:`~scpi_driver_core.scpi.engineering.parse_engineering_value`.

    Args:
        expected_unit: if given, the suffix must match it case-insensitively.
            A response without a suffix is always accepted.

    Raises:
        ResponseParseError: if there is no number, the number is non-finite and
            ``allow_non_finite`` is false, or the unit contradicts
            ``expected_unit``.
    """
    match = _VALUE_WITH_UNIT.match(response)
    if match is None:
        raise ResponseParseError(f"expected a number, got {response!r}", raw=response)

    value = parse_float(match.group("number"), allow_non_finite=allow_non_finite)
    unit = match.group("unit")

    if expected_unit is not None and unit and unit.casefold() != expected_unit.casefold():
        raise ResponseParseError(
            f"expected unit {expected_unit!r}, got {unit!r} in {response!r}", raw=response
        )
    return value


def parse_identity(response: str) -> Identity:
    """Parse a conventional comma-separated ``*IDN?`` reply.

    The usual shape is ``manufacturer,model,serial,firmware``. Instruments that
    supply fewer fields leave the optional ones as ``None``; fields beyond the
    fourth are ignored but remain visible in
    :attr:`~scpi_driver_core.models.Identity.raw`. Empty fields become ``None``
    rather than empty strings, except that a serial number an instrument
    reports literally as ``0`` is kept as written.

    Raises:
        IdentityError: if manufacturer and model are not both present.
    """
    try:
        fields = parse_csv(response)
    except ResponseParseError as exc:
        raise IdentityError(f"malformed *IDN? reply {response!r}") from exc

    trimmed = [field.strip() for field in fields]
    if len(trimmed) < 2 or not trimmed[0] or not trimmed[1]:
        raise IdentityError(f"*IDN? reply lacks manufacturer and model: {response!r}")

    def optional(index: int) -> str | None:
        if index >= len(trimmed) or not trimmed[index]:
            return None
        return trimmed[index]

    return Identity(
        manufacturer=trimmed[0],
        model=trimmed[1],
        serial_number=optional(2),
        firmware_version=optional(3),
        raw=response,
    )


def parse_scpi_error(response: str) -> ScpiError:
    """Parse a ``SYST:ERR?`` reply of the form ``code,"message"``.

    Raises:
        ResponseParseError: if the reply has no numeric code.
    """
    fields = parse_csv(response)
    if len(fields) < 2:
        raise ResponseParseError(f"expected a code and message, got {response!r}", raw=response)

    try:
        code = int(fields[0].strip())
    except ValueError as exc:
        raise ResponseParseError(
            f"expected a numeric error code, got {response!r}", raw=response
        ) from exc

    return ScpiError(code=code, message=",".join(fields[1:]).strip(), raw=response)


def quote_scpi_string(value: str) -> str:
    """Wrap ``value`` in the double quotes SCPI expects, doubling any it contains."""
    return '"' + value.replace('"', '""') + '"'
