from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import ResponseParseError
from scpi_driver_core.scpi import SI_PREFIXES, SUPPORTED_UNITS, parse_engineering_value

OHM_SIGN = "Ω"
GREEK_CAPITAL_OMEGA = "Ω"
MICRO_SIGN = "µ"
GREEK_MU = "μ"


@pytest.mark.parametrize(
    ("text", "value", "unit"),
    [
        ("12V", 12.0, "V"),
        ("500mA", 0.5, "A"),
        ("10uA", 1e-5, "A"),
        ("2.2k", 2200.0, ""),
        ("500ms", 0.5, "s"),
        ("1.5", 1.5, ""),
        ("-3V", -3.0, "V"),
        ("+3V", 3.0, "V"),
        ("1e3V", 1000.0, "V"),
        ("500 mA", 0.5, "A"),
        ("  12 V  ", 12.0, "V"),
        ("2.5MHz", 2.5e6, "Hz"),
        ("2.5mHz", 2.5e-3, "Hz"),
        ("1kohm", 1000.0, "Ohm"),
        ("4.7kOhms", 4700.0, "Ohm"),
        ("100nF", 1e-7, "F"),
        ("10mH", 1e-2, "H"),
        ("3W", 3.0, "W"),
        ("2.5 volts", 2.5, "V"),
        ("60 sec", 60.0, "s"),
        ("5amps", 5.0, "A"),
    ],
)
def test_parses_common_forms(text: str, value: float, unit: str) -> None:
    parsed = parse_engineering_value(text)
    assert parsed.value == pytest.approx(value)
    assert parsed.unit == unit
    assert parsed.raw == text


@pytest.mark.parametrize("symbol", [OHM_SIGN, GREEK_CAPITAL_OMEGA])
def test_both_omega_codepoints_are_ohms(symbol: str) -> None:
    parsed = parse_engineering_value(f"4.7k{symbol}")
    assert parsed.value == pytest.approx(4700.0)
    assert parsed.unit == "Ohm"


@pytest.mark.parametrize("symbol", [MICRO_SIGN, GREEK_MU])
def test_both_micro_codepoints_are_micro(symbol: str) -> None:
    assert parse_engineering_value(f"10{symbol}A").value == pytest.approx(1e-5)


def test_milli_and_mega_are_distinct() -> None:
    assert parse_engineering_value("1mA").value == pytest.approx(1e-3)
    assert parse_engineering_value("1MA").value == pytest.approx(1e6)


def test_both_kilo_spellings_are_accepted() -> None:
    assert parse_engineering_value("2K").value == parse_engineering_value("2k").value


def test_lowercase_single_char_unit_is_rejected() -> None:
    """'v' is rejected so that 'f' and 'a' can stay unambiguous prefixes."""
    with pytest.raises(ResponseParseError):
        parse_engineering_value("12v")


def test_single_char_prefixes_that_shadow_units() -> None:
    assert parse_engineering_value("1f").value == pytest.approx(1e-15)
    assert parse_engineering_value("1F").unit == "F"
    assert parse_engineering_value("1m").value == pytest.approx(1e-3)
    assert parse_engineering_value("1s").unit == "s"


def test_multi_char_units_are_case_insensitive() -> None:
    for text in ("50hz", "50Hz", "50HZ"):
        assert parse_engineering_value(text).unit == "Hz"


@pytest.mark.parametrize(
    "text", ["", "abc", "V", "12X", "12 furlongs", "12 mX", "1.2.3V", "12 V V"]
)
def test_rejects_unparsable(text: str) -> None:
    with pytest.raises(ResponseParseError) as excinfo:
        parse_engineering_value(text)
    assert excinfo.value.raw == text


def test_rejects_overflowing_magnitude() -> None:
    with pytest.raises(ResponseParseError):
        parse_engineering_value("1e999V")


def test_expected_unit_accepts_a_match() -> None:
    assert parse_engineering_value("500mA", expected_unit="A").value == pytest.approx(0.5)


def test_expected_unit_rejects_a_mismatch() -> None:
    with pytest.raises(ResponseParseError):
        parse_engineering_value("500mA", expected_unit="V")


def test_expected_unit_accepts_a_dimensionless_value() -> None:
    """'2.2k' where ohms are wanted is the common resistor shorthand."""
    assert parse_engineering_value("2.2k", expected_unit="Ohm").value == pytest.approx(2200)


def test_supported_units_matches_what_the_parser_produces() -> None:
    produced = {
        parse_engineering_value(text).unit
        for text in ("1V", "1A", "1W", "1F", "1H", "1s", "1ohm", "1hz")
    }
    assert produced <= SUPPORTED_UNITS


def test_prefix_table_is_read_only() -> None:
    """Public tables must not be mutable global state."""
    with pytest.raises(TypeError):
        SI_PREFIXES["z"] = 1e21  # type: ignore[index]


def test_result_is_immutable() -> None:
    parsed = parse_engineering_value("12V")
    with pytest.raises(AttributeError):
        parsed.value = 1.0  # type: ignore[misc]
