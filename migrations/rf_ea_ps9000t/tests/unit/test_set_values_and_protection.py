"""Set value and protection-threshold round-trips, and the device-error-not-
client-side-duplicated behavior.

task §12.1 items 4, 5, 6.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.exceptions import EaPs9000TDeviceError


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_voltage_current_power_round_trip(driver):
    driver.set_voltage(24.0)
    driver.set_current(5.0)
    driver.set_power(100.0)
    assert driver.get_voltage() == pytest.approx(24.0)
    assert driver.get_current() == pytest.approx(5.0)
    assert driver.get_power() == pytest.approx(100.0)


def test_protection_threshold_round_trip(driver):
    driver.set_overvoltage_protection(30.0)
    driver.set_overcurrent_protection(20.0)
    driver.set_overpower_protection(500.0)
    thresholds = driver.get_protection_thresholds()
    assert thresholds.overvoltage == pytest.approx(30.0)
    assert thresholds.overcurrent == pytest.approx(20.0)
    assert thresholds.overpower == pytest.approx(500.0)


def test_device_side_data_out_of_range_surfaces_as_typed_error(driver):
    """task §12.1 item 5: the device's own -222 is the source of truth."""

    driver.transport.simulator.force_data_out_of_range = True  # type: ignore[attr-defined]
    with pytest.raises(EaPs9000TDeviceError, match="Data out of range"):
        driver.set_voltage(1000.0)


def test_set_voltage_never_queries_limits_before_writing(driver, monkeypatch):
    """task §6 item 5 / §12.1 item 5: no client-side limit pre-validation.

    Assert the driver's own _query is never called with a LIMit command
    before the VOLTage write — the only permitted read after a set-value
    write is the error-queue check.
    """

    queried_commands: list[str] = []
    original_query = driver._query

    def tracking_query(command: str) -> str:
        queried_commands.append(command)
        return original_query(command)

    monkeypatch.setattr(driver, "_query", tracking_query)
    driver.set_voltage(10.0)

    assert not any("LIMit" in cmd for cmd in queried_commands)
    assert queried_commands == ["SYSTem:ERRor?"]


def test_value_outside_adjustment_limit_is_rejected_not_silently_applied(driver):
    """Setting an out-of-range value must not silently apply (task §6 item 5)."""

    driver.set_voltage_limit_high(20.0)
    with pytest.raises(EaPs9000TDeviceError, match="Data out of range"):
        driver.set_voltage(50.0)
    # The rejected value must not have been applied.
    assert driver.get_voltage() != 50.0
