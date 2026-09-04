"""Adjustment limit round-trips, including the asymmetric power-limit shape.

task §12.1 item 7.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_voltage_limit_round_trip(driver):
    driver.set_voltage_limit_low(1.0)
    driver.set_voltage_limit_high(50.0)
    assert driver.get_voltage_limits() == (1.0, 50.0)


def test_current_limit_round_trip(driver):
    driver.set_current_limit_low(0.5)
    driver.set_current_limit_high(30.0)
    assert driver.get_current_limits() == (0.5, 30.0)


def test_power_limit_high_round_trip_no_low_variant(driver):
    """task §12.1 item 7: no Set Power Limit Low exists at all on this instrument family."""

    driver.set_power_limit_high(800.0)
    assert driver.get_power_limit_high() == 800.0

    assert not hasattr(driver, "set_power_limit_low")
    assert not hasattr(driver, "get_power_limit_low")


def test_get_adjustment_limits_snapshot(driver):
    driver.set_voltage_limit_high(50.0)
    driver.set_current_limit_high(30.0)
    driver.set_power_limit_high(800.0)
    limits = driver.get_adjustment_limits()
    assert limits.voltage_high == 50.0
    assert limits.current_high == 30.0
    assert limits.power_high == 800.0
