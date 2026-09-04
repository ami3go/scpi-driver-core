"""Measuring commands and general queries.

Supports task §12.1 coverage of §8 keywords (measuring, nominal ratings, device class).
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_measured_values_default_to_zero(driver):
    assert driver.get_measured_voltage() == 0.0
    assert driver.get_measured_current() == 0.0
    assert driver.get_measured_power() == 0.0


def test_measured_array_round_trip_via_simulator_hook(driver):
    driver.transport.simulator.measured.voltage = 12.5  # type: ignore[attr-defined]
    driver.transport.simulator.measured.current = 3.3  # type: ignore[attr-defined]
    driver.transport.simulator.measured.power = 41.25  # type: ignore[attr-defined]

    values = driver.get_measured_values()
    assert values.voltage == pytest.approx(12.5)
    assert values.current == pytest.approx(3.3)
    assert values.power == pytest.approx(41.25)

    assert driver.get_measured_voltage() == pytest.approx(12.5)


def test_nominal_ratings_reflect_the_connected_unit(driver):
    """The correct way to discover ratings is a query, never a hardcoded constant (task §1)."""

    ratings = driver.get_nominal_ratings()
    assert ratings.voltage > 0
    assert ratings.current > 0
    assert ratings.power > 0


def test_device_class_is_queryable(driver):
    assert driver.get_device_class()
