"""Overload sentinel handling.

task §14.1 item 3, task §6 item 3.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.exceptions import Agilent34411AOverloadError


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_get_immediate_measurement_raises_overload_error(driver):
    driver.transport.simulator.force_overload = True  # type: ignore[attr-defined]
    with pytest.raises(Agilent34411AOverloadError):
        driver.get_immediate_measurement()


def test_get_reading_raises_overload_error(driver):
    driver.transport.simulator.force_overload = True  # type: ignore[attr-defined]
    driver._write("INITiate")  # populate reading memory without checking overload
    with pytest.raises(Agilent34411AOverloadError):
        driver.get_reading()


def test_get_most_recent_reading_raises_overload_error(driver):
    driver.transport.simulator.force_overload = True  # type: ignore[attr-defined]
    driver._write("INITiate")
    with pytest.raises(Agilent34411AOverloadError):
        driver.get_most_recent_reading()


def test_normal_reading_does_not_raise(driver):
    value = driver.get_immediate_measurement()
    assert isinstance(value, float)
    assert abs(value) < 1e6
