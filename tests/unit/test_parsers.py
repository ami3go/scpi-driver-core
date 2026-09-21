from __future__ import annotations

import math

import pytest

from scpi_driver_core.exceptions import ConfigurationError, IdentityError, ResponseParseError
from scpi_driver_core.scpi import (
    parse_bool,
    parse_csv,
    parse_csv_floats,
    parse_float,
    parse_identity,
    parse_int,
    parse_optional_unit_float,
    parse_scpi_error,
    quote_scpi_string,
)

# -- floats ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("1.5", 1.5),
        ("  1.5  ", 1.5),
        ("+1.04858000E+00", 1.04858),
        ("-3.2e-4", -3.2e-4),
        ("0", 0.0),
        ("-0", 0.0),
    ],
)
def test_parse_float(response: str, expected: float) -> None:
    assert parse_float(response) == pytest.approx(expected)


@pytest.mark.parametrize("response", ["", "  ", "abc", "1.2.3", "1,2", "12V", "None"])
def test_parse_float_rejects_malformed(response: str) -> None:
    with pytest.raises(ResponseParseError) as excinfo:
        parse_float(response)
    assert excinfo.value.raw == response


@pytest.mark.parametrize(
    "response",
    ["nan", "inf", "-inf", "NaN", "Infinity", "9.9E37", "+9.90000000E+37", "-9.9E37", "9.91E37"],
)
def test_parse_float_rejects_non_finite_by_default(response: str) -> None:
    with pytest.raises(ResponseParseError):
        parse_float(response)


def test_parse_float_can_allow_non_finite() -> None:
    assert parse_float("inf", allow_non_finite=True) == float("inf")
    assert parse_float("9.9E37", allow_non_finite=True) == math.inf
    assert parse_float("-9.9E37", allow_non_finite=True) == -math.inf
    assert math.isnan(parse_float("9.91E37", allow_non_finite=True))


def test_parse_float_can_disable_scpi_special_mapping() -> None:
    assert parse_float("9.9E37", scpi_special_values=False) == pytest.approx(9.9e37)


def test_parse_float_never_coerces_to_zero() -> None:
    with pytest.raises(ResponseParseError):
        parse_float("OVERLOAD")


@pytest.mark.parametrize("response", ["1_000", "٣.٥", "0x10"])
def test_parse_float_rejects_non_scpi_numeric_syntax(response: str) -> None:
    with pytest.raises(ResponseParseError):
        parse_float(response)


# -- integers -------------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("5", 5),
        (" -12 ", -12),
        ("+7", 7),
        ("1.00000000E+02", 100),
        ("12345678901234567.0", 12345678901234567),
        ("0", 0),
    ],
)
def test_parse_int(response: str, expected: int) -> None:
    assert parse_int(response) == expected


@pytest.mark.parametrize("response", ["1.5", "abc", "", "nan", "inf", "1e999", "1_000", "٣"])
def test_parse_int_rejects_non_integers(response: str) -> None:
    with pytest.raises(ResponseParseError):
        parse_int(response)


# -- booleans -------------------------------------------------------------


@pytest.mark.parametrize("response", ["1", "ON", "on", "On", "TRUE", "true", " 1 ", "1.000000E+00"])
def test_parse_bool_true(response: str) -> None:
    assert parse_bool(response) is True


@pytest.mark.parametrize("response", ["0", "OFF", "off", "FALSE", "false", "0.0"])
def test_parse_bool_false(response: str) -> None:
    assert parse_bool(response) is False


@pytest.mark.parametrize("response", ["2", "-1", "YES", "", "maybe", "1.5"])
def test_parse_bool_rejects_other_values(response: str) -> None:
    with pytest.raises(ResponseParseError):
        parse_bool(response)


# -- CSV ------------------------------------------------------------------


def test_parse_csv_simple() -> None:
    assert parse_csv("1.0,2.0,3.0") == ["1.0", "2.0", "3.0"]


def test_parse_csv_skips_space_after_separator() -> None:
    assert parse_csv("1.0, 2.0, 3.0") == ["1.0", "2.0", "3.0"]


def test_parse_csv_honors_quoted_commas() -> None:
    assert parse_csv('-113,"Undefined header, near VOLT"') == [
        "-113",
        "Undefined header, near VOLT",
    ]


def test_parse_csv_preserves_spaces_inside_quotes() -> None:
    assert parse_csv('"a b ",c') == ["a b ", "c"]


def test_parse_csv_single_field() -> None:
    assert parse_csv("42") == ["42"]


@pytest.mark.parametrize("response", ["", "   "])
def test_parse_csv_empty(response: str) -> None:
    assert parse_csv(response) == []


def test_parse_csv_keeps_empty_fields() -> None:
    assert parse_csv("1,,3") == ["1", "", "3"]


def test_parse_csv_rejects_a_stray_carriage_return() -> None:
    with pytest.raises(ResponseParseError) as excinfo:
        parse_csv("a\rb,c")
    assert excinfo.value.raw == "a\rb,c"


# -- CSV floats -----------------------------------------------------------


def test_parse_csv_floats_multi_channel() -> None:
    assert parse_csv_floats("3.301,3.298,3.305") == [3.301, 3.298, 3.305]


def test_parse_csv_floats_single_field() -> None:
    assert parse_csv_floats("3.301") == [3.301]


def test_parse_csv_floats_empty_response_yields_empty_list() -> None:
    assert parse_csv_floats("") == []


def test_parse_csv_floats_rejects_a_non_numeric_field() -> None:
    with pytest.raises(ResponseParseError):
        parse_csv_floats("1.0,not-a-number,3.0")


def test_parse_csv_floats_rejects_non_finite_by_default() -> None:
    with pytest.raises(ResponseParseError):
        parse_csv_floats("1.0,INF,3.0")


def test_parse_csv_floats_allows_non_finite_when_asked() -> None:
    assert parse_csv_floats("1.0,INF,3.0", allow_non_finite=True) == [1.0, math.inf, 3.0]


# -- identity -------------------------------------------------------------


def test_parse_identity_full() -> None:
    identity = parse_identity("KEYSIGHT,N6700C,MY56000102,D.01.09")
    assert identity.manufacturer == "KEYSIGHT"
    assert identity.model == "N6700C"
    assert identity.serial_number == "MY56000102"
    assert identity.firmware_version == "D.01.09"
    assert identity.raw == "KEYSIGHT,N6700C,MY56000102,D.01.09"


def test_parse_identity_hp_style_zero_serial() -> None:
    identity = parse_identity("HEWLETT-PACKARD,34401A,0,11-5-2")
    assert identity.serial_number == "0"
    assert identity.firmware_version == "11-5-2"


def test_parse_identity_two_fields() -> None:
    identity = parse_identity("EA-Elektro-Automatik,PS9080-100")
    assert identity.serial_number is None
    assert identity.firmware_version is None


def test_parse_identity_three_fields() -> None:
    assert parse_identity("A,B,C").firmware_version is None


def test_parse_identity_tolerates_padding() -> None:
    identity = parse_identity(" TEKTRONIX , TBS1052C , C012345 , CF:91.1CT ")
    assert identity.manufacturer == "TEKTRONIX"
    assert identity.model == "TBS1052C"


def test_parse_identity_ignores_extra_fields_but_keeps_raw() -> None:
    raw = "A,B,C,D,E,F"
    identity = parse_identity(raw)
    assert identity.firmware_version == "D"
    assert identity.raw == raw


def test_parse_identity_treats_empty_optional_fields_as_none() -> None:
    identity = parse_identity("A,B,,")
    assert identity.serial_number is None
    assert identity.firmware_version is None


@pytest.mark.parametrize("response", ["", "OnlyOne", ",B", "A,", " , "])
def test_parse_identity_rejects_incomplete(response: str) -> None:
    with pytest.raises(IdentityError):
        parse_identity(response)


def test_parse_identity_reports_unparsable_reply_as_identity_error() -> None:
    with pytest.raises(IdentityError):
        parse_identity("KEYSIGHT\r,N6700C")


# -- SCPI errors ----------------------------------------------------------


def test_parse_scpi_error_no_error() -> None:
    error = parse_scpi_error('0,"No error"')
    assert error.code == 0
    assert error.message == "No error"


def test_parse_scpi_error_negative_code() -> None:
    error = parse_scpi_error('-113,"Undefined header"')
    assert error.code == -113
    assert error.message == "Undefined header"


def test_parse_scpi_error_message_containing_comma() -> None:
    error = parse_scpi_error('-113,"Undefined header, near VOLT"')
    assert error.message == "Undefined header, near VOLT"


def test_parse_scpi_error_unquoted_message() -> None:
    assert parse_scpi_error("0,No error").message == "No error"


def test_parse_scpi_error_retains_raw() -> None:
    raw = '  -222 , "Data out of range"  '
    assert parse_scpi_error(raw).raw == raw


@pytest.mark.parametrize("response", ["", "no code", '"just a message"', "abc,def"])
def test_parse_scpi_error_rejects_malformed(response: str) -> None:
    with pytest.raises(ResponseParseError):
        parse_scpi_error(response)


# -- optional unit --------------------------------------------------------


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("500.0", 500.0),
        ("500.0 V", 500.0),
        ("500.0V", 500.0),
        ("  -1.5E+01 A  ", -15.0),
        ("12 Ohm", 12.0),
    ],
)
def test_parse_optional_unit_float(response: str, expected: float) -> None:
    assert parse_optional_unit_float(response) == pytest.approx(expected)


def test_parse_optional_unit_float_accepts_matching_unit() -> None:
    assert parse_optional_unit_float("500.0 V", expected_unit="V") == 500.0


def test_parse_optional_unit_float_accepts_missing_unit() -> None:
    assert parse_optional_unit_float("500.0", expected_unit="V") == 500.0


def test_parse_optional_unit_float_is_case_insensitive_about_units() -> None:
    assert parse_optional_unit_float("500.0 v", expected_unit="V") == 500.0


def test_parse_optional_unit_float_rejects_wrong_unit() -> None:
    with pytest.raises(ResponseParseError):
        parse_optional_unit_float("500.0 A", expected_unit="V")


@pytest.mark.parametrize("response", ["", "V", "abc", "1.5 V extra", "1 2"])
def test_parse_optional_unit_float_rejects_malformed(response: str) -> None:
    with pytest.raises(ResponseParseError):
        parse_optional_unit_float(response)


def test_parse_optional_unit_float_rejects_non_finite() -> None:
    with pytest.raises(ResponseParseError):
        parse_optional_unit_float("1e999")


@pytest.mark.parametrize("response", ["INF V", "-Infinity A", "NaN Hz"])
def test_parse_optional_unit_float_allows_explicit_non_finite(response: str) -> None:
    assert not math.isfinite(parse_optional_unit_float(response, allow_non_finite=True))


def test_parse_optional_unit_float_does_not_scale_prefixes() -> None:
    assert parse_optional_unit_float("500 mV") == 500.0


# -- quoting --------------------------------------------------------------


def test_quote_scpi_string() -> None:
    assert quote_scpi_string("SETUP1") == '"SETUP1"'


def test_quote_scpi_string_doubles_embedded_quotes() -> None:
    assert quote_scpi_string('say "hi"') == '"say ""hi"""'


def test_quote_scpi_string_empty() -> None:
    assert quote_scpi_string("") == '""'


@pytest.mark.parametrize("value", ["a\nb", "a\rb", "a\r\nb"])
def test_quote_scpi_string_rejects_line_breaks(value: str) -> None:
    with pytest.raises(ConfigurationError):
        quote_scpi_string(value)
