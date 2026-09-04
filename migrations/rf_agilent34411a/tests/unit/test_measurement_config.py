"""Per-function measurement configuration round-trips.

task §14.1 item 2.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.enums import AcFilter, AutoZeroMode, Function
from agilent34411a.exceptions import Agilent34411AValidationError


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_dc_voltage_round_trip(driver):
    driver.set_range(Function.DC_VOLTAGE, 10.0)
    assert driver.get_range(Function.DC_VOLTAGE) == 10.0
    assert driver.get_auto_range(Function.DC_VOLTAGE) is False

    driver.set_auto_range(Function.DC_VOLTAGE, True)
    assert driver.get_auto_range(Function.DC_VOLTAGE) is True

    driver.set_integration_time_nplc(Function.DC_VOLTAGE, 10.0)
    assert driver.get_integration_time_nplc(Function.DC_VOLTAGE) == 10.0

    driver.set_integration_time_aperture(Function.DC_VOLTAGE, 0.5)
    assert driver.get_integration_time_aperture(Function.DC_VOLTAGE) == pytest.approx(0.5)

    driver.set_auto_zero(Function.DC_VOLTAGE, AutoZeroMode.OFF)
    assert driver.get_auto_zero(Function.DC_VOLTAGE) == AutoZeroMode.OFF

    driver.set_input_impedance_auto(True)
    assert driver.get_input_impedance_auto() is True


def test_ac_voltage_round_trip(driver):
    driver.set_range(Function.AC_VOLTAGE, 1.0)
    assert driver.get_range(Function.AC_VOLTAGE) == 1.0

    driver.set_ac_filter_bandwidth(Function.AC_VOLTAGE, AcFilter.SLOW)
    assert driver.get_ac_filter_bandwidth(Function.AC_VOLTAGE) == AcFilter.SLOW

    driver.set_null(Function.AC_VOLTAGE, True)
    assert driver.get_null(Function.AC_VOLTAGE) is True
    driver.set_null_value(Function.AC_VOLTAGE, 0.05)
    assert driver.get_null_value(Function.AC_VOLTAGE) == pytest.approx(0.05)


def test_four_wire_resistance_round_trip(driver):
    driver.set_range(Function.RESISTANCE_4W, 1000.0)
    assert driver.get_range(Function.RESISTANCE_4W) == 1000.0

    driver.set_offset_compensation(Function.RESISTANCE_4W, True)
    assert driver.get_offset_compensation(Function.RESISTANCE_4W) is True

    driver.set_integration_time_nplc(Function.RESISTANCE_4W, 100.0)
    assert driver.get_integration_time_nplc(Function.RESISTANCE_4W) == 100.0


def test_four_wire_resistance_rejects_explicit_auto_zero(driver):
    """task §8: 4-wire resistance is always auto-zero on; no ZERO:AUTO command exists."""

    with pytest.raises(Agilent34411AValidationError, match="always auto-zero on"):
        driver.set_auto_zero(Function.RESISTANCE_4W, AutoZeroMode.ON)


def test_frequency_round_trip(driver):
    """Frequency uses gate time (aperture only, no NPLC) and the ac-voltage range/bandwidth path."""

    driver.set_integration_time_aperture(Function.FREQUENCY, 0.1)
    assert driver.get_integration_time_aperture(Function.FREQUENCY) == pytest.approx(0.1)

    with pytest.raises(Agilent34411AValidationError):
        driver.set_integration_time_nplc(Function.FREQUENCY, 1.0)

    driver.set_range(Function.FREQUENCY, 1.0)
    assert driver.get_range(Function.FREQUENCY) == 1.0

    driver.set_ac_filter_bandwidth(Function.FREQUENCY, AcFilter.FAST)
    assert driver.get_ac_filter_bandwidth(Function.FREQUENCY) == AcFilter.FAST
    # Frequency shares the ac-voltage bandwidth setting (task §8) — confirm it's the same value.
    assert driver.get_ac_filter_bandwidth(Function.AC_VOLTAGE) == AcFilter.FAST


def test_capacitance_has_no_integration_time_setting(driver):
    with pytest.raises(Agilent34411AValidationError):
        driver.set_integration_time_nplc(Function.CAPACITANCE, 1.0)
    with pytest.raises(Agilent34411AValidationError):
        driver.set_integration_time_aperture(Function.CAPACITANCE, 1.0)


def test_get_measurement_settings_snapshot(driver):
    driver.set_function(Function.DC_VOLTAGE)
    driver.set_range(Function.DC_VOLTAGE, 10.0)
    settings = driver.get_measurement_settings()
    assert settings.function == "VOLT"
    assert settings.range_value == 10.0
    assert settings.offset_compensation is None  # not applicable to DC voltage
