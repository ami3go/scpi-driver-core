"""Calibration commands (Gate 3 extension — CALibration subsystem): the
two-tier safety guard, the instrument's own security-code lock, and the
line-frequency/value/string/count round-trips.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.exceptions import Agilent34411ADeviceError, Agilent34411AValidationError

_DEFAULT_SECURITY_CODE = "AT34411A"


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def _unlocked(driver: Agilent34411A) -> Agilent34411A:
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    driver.unlock_calibration(_DEFAULT_SECURITY_CODE)
    return driver


# ------------------------------------------------------------------
# Two-tier guard
# ------------------------------------------------------------------
def test_calibration_methods_are_rejected_before_enable_calibration_mode(driver):
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.unlock_calibration(_DEFAULT_SECURITY_CODE)
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.lock_calibration()
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.set_calibration_security_code("NEWCODE1")
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.run_full_calibration()
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.run_adc_calibration()
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.set_calibration_line_frequency(60)
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.get_calibration_line_frequency()
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.store_calibration()
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.set_calibration_string("hello")
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.get_calibration_string()
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.set_calibration_value(1.0)
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.get_calibration_value()


def test_read_only_calibration_queries_do_not_require_the_guard(driver):
    """is_calibration_locked, get_calibration_count, and the actual-line-frequency
    readback are harmless reads."""

    assert driver.is_calibration_locked() is True
    assert driver.get_calibration_count() == 3  # simulator factory default
    assert driver.get_actual_calibration_line_frequency() == pytest.approx(50.0)


def test_enable_calibration_mode_rejects_wrong_confirmation_text(driver):
    with pytest.raises(Agilent34411AValidationError, match="confirmation"):
        driver.enable_calibration_mode("yes please")


def test_enable_calibration_mode_rejects_the_raw_scpi_phrase(driver):
    """The two guards use deliberately different phrases: satisfying one must
    not satisfy the other."""

    with pytest.raises(Agilent34411AValidationError, match="confirmation"):
        driver.enable_calibration_mode("ENABLE RAW SCPI")
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.run_full_calibration()


def test_enable_raw_scpi_does_not_unlock_calibration(driver):
    driver.enable_raw_scpi("ENABLE RAW SCPI")
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.run_full_calibration()


def test_enable_calibration_mode_with_exact_text_unlocks_the_guard(driver):
    _unlocked(driver)
    assert driver.run_full_calibration() is True


# ------------------------------------------------------------------
# run_full_calibration / run_adc_calibration pass/fail
# ------------------------------------------------------------------
def test_run_full_calibration_requires_unlocked_instrument(driver):
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.run_full_calibration()


def test_run_full_calibration_pass_increments_count(driver):
    _unlocked(driver)
    count_before = driver.get_calibration_count()
    assert driver.run_full_calibration() is True
    assert driver.get_calibration_count() == count_before + 1


def test_run_full_calibration_forced_failure(driver):
    _unlocked(driver)
    driver.transport.simulator.force_calibration_failure = True  # type: ignore[attr-defined]
    assert driver.run_full_calibration() is False


def test_run_adc_calibration_requires_unlocked_instrument(driver):
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.run_adc_calibration()


def test_run_adc_calibration_returns_a_float(driver):
    _unlocked(driver)
    assert driver.run_adc_calibration() == pytest.approx(1.0e-6)


# ------------------------------------------------------------------
# Lock/unlock round trip
# ------------------------------------------------------------------
def test_unlock_calibration_with_wrong_code_raises_device_error(driver):
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    with pytest.raises(Agilent34411ADeviceError, match="invalid"):
        driver.unlock_calibration("WRONGCODE")
    assert driver.is_calibration_locked() is True


def test_lock_calibration_does_not_require_a_code(driver):
    _unlocked(driver)
    assert driver.is_calibration_locked() is False
    driver.lock_calibration()
    assert driver.is_calibration_locked() is True


def test_set_calibration_security_code_round_trip(driver):
    _unlocked(driver)
    driver.set_calibration_security_code("NEWCODE1")
    driver.lock_calibration()
    driver.unlock_calibration("NEWCODE1")
    assert driver.is_calibration_locked() is False


def test_calibration_writes_are_rejected_once_locked(driver):
    _unlocked(driver)
    driver.lock_calibration()
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.set_calibration_value(2.0)
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.set_calibration_string("x")
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.set_calibration_security_code("OTHER1")
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.store_calibration()
    with pytest.raises(Agilent34411ADeviceError, match="secured"):
        driver.set_calibration_line_frequency(60)


# ------------------------------------------------------------------
# Line frequency / value / string / count round trips
# ------------------------------------------------------------------
def test_calibration_line_frequency_round_trip(driver):
    _unlocked(driver)
    assert driver.get_calibration_line_frequency() == 50  # simulator factory default
    driver.set_calibration_line_frequency(60)
    assert driver.get_calibration_line_frequency() == 60


def test_calibration_line_frequency_rejects_invalid_values(driver):
    _unlocked(driver)
    with pytest.raises(Agilent34411AValidationError, match="50 or 60"):
        driver.set_calibration_line_frequency(45)


def test_calibration_value_round_trip(driver):
    _unlocked(driver)
    driver.set_calibration_value(3.14159)
    assert driver.get_calibration_value() == pytest.approx(3.14159)


def test_calibration_string_round_trip(driver):
    _unlocked(driver)
    driver.set_calibration_string("Cal Due: 01 August 2027")
    assert driver.get_calibration_string() == "Cal Due: 01 August 2027"


def test_store_calibration(driver):
    _unlocked(driver)
    driver.store_calibration()  # no exception, no return value


# ------------------------------------------------------------------
# Robot library wiring
# ------------------------------------------------------------------
def test_library_calibration_keywords_go_through_the_same_two_tier_guard():
    from rf_agilent34411a.library import Agilent34411ALibrary

    lib = Agilent34411ALibrary()
    lib.connect(alias="dmm1", simulated=True)
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        lib.run_full_calibration(alias="dmm1")

    lib.enable_calibration_mode("ENABLE CALIBRATION", alias="dmm1")
    lib.unlock_calibration(_DEFAULT_SECURITY_CODE, alias="dmm1")
    assert lib.run_full_calibration(alias="dmm1") is True
    lib.disconnect("dmm1")


def test_library_is_calibration_locked_does_not_require_the_guard():
    from rf_agilent34411a.library import Agilent34411ALibrary

    lib = Agilent34411ALibrary()
    lib.connect(alias="dmm1", simulated=True)
    assert lib.is_calibration_locked(alias="dmm1") is True
    lib.disconnect("dmm1")
