"""Math (CALCulate) function round-trips and mutual exclusivity.

task §14.1 items 5, 6, 7.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.enums import MathFunction
from agilent34411a.exceptions import Agilent34411AValidationError


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_db_measurement_round_trip(driver):
    driver.enable_db_measurement()
    assert driver.get_math_function() == MathFunction.DB
    assert driver.is_math_enabled() is True
    driver.set_db_reference(1.5)
    driver.disable_math()
    assert driver.is_math_enabled() is False


def test_dbm_measurement_round_trip(driver):
    driver.enable_dbm_measurement()
    assert driver.get_math_function() == MathFunction.DBM
    driver.set_dbm_reference_resistance(600)


def test_dbm_reference_resistance_rejects_undocumented_value(driver):
    """task §14.1 item 6: reject before any device write."""

    with pytest.raises(Agilent34411AValidationError):
        driver.set_dbm_reference_resistance(123)


def test_math_functions_are_mutually_exclusive(driver):
    """task §14.1 item 5: enabling one deselects any previously active one."""

    driver.enable_db_measurement()
    assert driver.get_math_function() == MathFunction.DB

    driver.enable_statistics()
    assert driver.get_math_function() == MathFunction.STATISTICS

    driver.enable_limit_test()
    assert driver.get_math_function() == MathFunction.LIMIT


def test_statistics_accumulate_across_readings(driver):
    driver.enable_statistics()
    for _ in range(4):
        driver.get_immediate_measurement()
    stats = driver.get_statistics()
    assert stats.count == 4
    assert stats.average == pytest.approx(stats.minimum)  # simulator returns a fixed value
    driver.clear_statistics()
    assert driver.get_statistics().count == 0


def test_limits_reject_low_greater_or_equal_to_high(driver):
    """task §14.1 item 7: reject before any device write."""

    with pytest.raises(Agilent34411AValidationError):
        driver.set_limits(10.0, 10.0)
    with pytest.raises(Agilent34411AValidationError):
        driver.set_limits(10.0, 5.0)


def test_limits_round_trip(driver):
    driver.enable_limit_test()
    driver.set_limits(-1.0, 1.0)
    assert driver.get_limits() == (-1.0, 1.0)
