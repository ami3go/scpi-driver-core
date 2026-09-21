from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.scpi import (
    parse_csv,
    parse_engineering_value,
    parse_float,
    parse_int,
    parse_optional_unit_float,
    quote_scpi_string,
)

pytestmark = pytest.mark.property

_FINITE_FLOATS = st.floats(
    min_value=-1.0e12,
    max_value=1.0e12,
    allow_nan=False,
    allow_infinity=False,
)
_SCPI_STRING_TEXT = st.text(
    alphabet=st.sampled_from(list('abcXYZ0123456789 ,"_-+/.:;\t')),
    max_size=128,
)
_PREFIXES = st.sampled_from(
    [
        ("f", 1e-15),
        ("p", 1e-12),
        ("n", 1e-9),
        ("u", 1e-6),
        ("m", 1e-3),
        ("k", 1e3),
        ("M", 1e6),
        ("G", 1e9),
    ]
)


@given(value=_FINITE_FLOATS)
def test_float_parser_round_trips_finite_values(value: float) -> None:
    assert parse_float(repr(value)) == value


@given(value=st.integers(min_value=-(10**18), max_value=10**18))
def test_integer_parser_round_trips_decimal_values(value: int) -> None:
    assert parse_int(str(value)) == value


@given(value=_SCPI_STRING_TEXT)
def test_scpi_quoted_string_round_trips_through_csv_parser(value: str) -> None:
    assert parse_csv(quote_scpi_string(value)) == [value]


@given(value=st.text(alphabet=st.sampled_from(["\r", "\n"]), min_size=1, max_size=8))
def test_scpi_quoted_string_rejects_line_breaks(value: str) -> None:
    with pytest.raises(ConfigurationError):
        quote_scpi_string(value)


@given(value=_FINITE_FLOATS)
def test_optional_unit_float_accepts_equivalent_unit_case(value: float) -> None:
    assert parse_optional_unit_float(f"{value!r} V", expected_unit="v") == value


@given(value=_FINITE_FLOATS, prefix_and_scale=_PREFIXES)
def test_engineering_prefix_scaling(value: float, prefix_and_scale: tuple[str, float]) -> None:
    prefix, scale = prefix_and_scale
    parsed = parse_engineering_value(f"{value!r}{prefix}V", expected_unit="V")

    assert parsed.unit == "V"
    assert parsed.value == pytest.approx(value * scale)
