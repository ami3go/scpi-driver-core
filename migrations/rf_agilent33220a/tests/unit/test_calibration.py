"""Calibration commands (Gate 3): the two-tier safety guard, pass/fail paths,
client-side validation, and calibration step/value/count/string round-trips.
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220ADeviceError, Agilent33220AValidationError
from rf_agilent33220a.library import Agilent33220ALibrary

_DEFAULT_SECURITY_CODE = "AT33220A"


@pytest.fixture()
def driver():
    d = Agilent33220A.connect_simulated()
    yield d
    d.close()


def _unlocked(driver: Agilent33220A) -> Agilent33220A:
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    driver.unlock_calibration(_DEFAULT_SECURITY_CODE)
    return driver


# ------------------------------------------------------------------
# Two-tier guard
# ------------------------------------------------------------------
def test_calibration_methods_are_rejected_before_enable_calibration_mode(driver):
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.run_calibration()
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.unlock_calibration(_DEFAULT_SECURITY_CODE)
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.lock_calibration()
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.set_calibration_security_code("NEWCODE1")
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.set_calibration_step(1)
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.set_calibration_value(1.0)
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.set_calibration_string("hello")


def test_read_only_calibration_queries_do_not_require_the_guard(driver):
    """is_calibration_locked and get_calibration_count are harmless reads."""

    assert driver.is_calibration_locked() is True
    assert driver.get_calibration_count() == 0


def test_enable_calibration_mode_rejects_wrong_confirmation_text(driver):
    with pytest.raises(Agilent33220AValidationError, match="confirmation"):
        driver.enable_calibration_mode("yes please")


def test_enable_calibration_mode_rejects_the_raw_scpi_phrase(driver):
    """The two guards use deliberately different phrases: satisfying one must
    not satisfy the other."""

    with pytest.raises(Agilent33220AValidationError, match="confirmation"):
        driver.enable_calibration_mode("ENABLE RAW SCPI")
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.run_calibration()


def test_enable_raw_scpi_does_not_unlock_calibration(driver):
    driver.enable_raw_scpi("ENABLE RAW SCPI")
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.run_calibration()


def test_enable_calibration_mode_with_exact_text_unlocks_the_guard(driver):
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    driver.unlock_calibration(_DEFAULT_SECURITY_CODE)
    assert driver.run_calibration() is True


# ------------------------------------------------------------------
# run_calibration pass/fail
# ------------------------------------------------------------------
def test_run_calibration_requires_unlocked_instrument(driver):
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    with pytest.raises(Agilent33220ADeviceError, match="secured"):
        driver.run_calibration()


def test_run_calibration_pass(driver):
    _unlocked(driver)
    assert driver.run_calibration() is True
    assert driver.get_calibration_count() == 1


def test_run_calibration_forced_failure(driver):
    _unlocked(driver)
    driver.transport.simulator.force_calibration_failure = True  # type: ignore[attr-defined]
    assert driver.run_calibration() is False


# ------------------------------------------------------------------
# Lock/unlock round trip
# ------------------------------------------------------------------
def test_unlock_calibration_with_wrong_code_raises_device_error(driver):
    driver.enable_calibration_mode("ENABLE CALIBRATION")
    with pytest.raises(Agilent33220ADeviceError, match="invalid"):
        driver.unlock_calibration("WRONGCODE")
    assert driver.is_calibration_locked() is True


def test_lock_calibration_does_not_require_a_code(driver):
    _unlocked(driver)
    assert driver.is_calibration_locked() is False
    driver.lock_calibration()
    assert driver.is_calibration_locked() is True


# ------------------------------------------------------------------
# Security code validation (before any device I/O)
# ------------------------------------------------------------------
def test_set_calibration_security_code_rejects_empty(driver):
    _unlocked(driver)
    with pytest.raises(Agilent33220AValidationError, match="1-12 characters"):
        driver.set_calibration_security_code("")


def test_set_calibration_security_code_rejects_code_not_starting_with_a_letter(driver):
    _unlocked(driver)
    with pytest.raises(Agilent33220AValidationError, match="letter"):
        driver.set_calibration_security_code("1ABC")


def test_set_calibration_security_code_rejects_more_than_12_characters(driver):
    _unlocked(driver)
    with pytest.raises(Agilent33220AValidationError, match="1-12 characters"):
        driver.set_calibration_security_code("A" * 13)


def test_set_calibration_security_code_rejects_invalid_characters(driver):
    _unlocked(driver)
    with pytest.raises(Agilent33220AValidationError, match="letters, digits, or underscore"):
        driver.set_calibration_security_code("AB CD")


def test_set_calibration_security_code_accepts_a_valid_code(driver):
    _unlocked(driver)
    driver.set_calibration_security_code("NEW_CODE1")
    driver.lock_calibration()
    driver.unlock_calibration("NEW_CODE1")
    assert driver.is_calibration_locked() is False


# ------------------------------------------------------------------
# Step / value / count / string round trips
# ------------------------------------------------------------------
def test_calibration_step_round_trip(driver):
    _unlocked(driver)
    driver.set_calibration_step(42)
    assert driver.get_calibration_step() == 42


def test_calibration_step_rejects_out_of_range(driver):
    _unlocked(driver)
    with pytest.raises(Agilent33220AValidationError, match="0 and 94"):
        driver.set_calibration_step(95)
    with pytest.raises(Agilent33220AValidationError, match="0 and 94"):
        driver.set_calibration_step(-1)


def test_calibration_value_round_trip(driver):
    _unlocked(driver)
    driver.set_calibration_value(3.14159)
    assert driver.get_calibration_value() == pytest.approx(3.14159)


def test_calibration_count_increments_on_run(driver):
    _unlocked(driver)
    assert driver.get_calibration_count() == 0
    driver.run_calibration()
    driver.run_calibration()
    assert driver.get_calibration_count() == 2


def test_calibration_string_round_trip(driver):
    _unlocked(driver)
    driver.set_calibration_string("Cal Due: 01 August 2027")
    assert driver.get_calibration_string() == "Cal Due: 01 August 2027"


def test_calibration_string_rejects_more_than_40_characters(driver):
    _unlocked(driver)
    with pytest.raises(Agilent33220AValidationError, match="40 characters"):
        driver.set_calibration_string("x" * 41)


# ------------------------------------------------------------------
# Robot library wiring
# ------------------------------------------------------------------
def test_library_calibration_keywords_go_through_the_same_two_tier_guard():
    lib = Agilent33220ALibrary()
    lib.connect(alias="gen1", simulated=True)
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        lib.run_calibration(alias="gen1")

    lib.enable_calibration_mode("ENABLE CALIBRATION", alias="gen1")
    lib.unlock_calibration(_DEFAULT_SECURITY_CODE, alias="gen1")
    assert lib.run_calibration(alias="gen1") is True
    lib.disconnect("gen1")


def test_library_is_calibration_locked_does_not_require_the_guard():
    lib = Agilent33220ALibrary()
    lib.connect(alias="gen1", simulated=True)
    assert lib.is_calibration_locked(alias="gen1") is True
    lib.disconnect("gen1")
