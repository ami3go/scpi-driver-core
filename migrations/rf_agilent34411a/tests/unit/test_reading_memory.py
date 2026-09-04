"""Volatile and non-volatile reading memory round-trips.

task §14.1 item 13.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_reading_count_and_latest_reading(driver):
    driver.set_sample_count(3)
    driver.get_immediate_measurement()
    assert driver.get_reading_count() == 3
    assert driver.get_most_recent_reading() == pytest.approx(1.234567)


def test_drain_readings_is_destructive_fifo(driver):
    driver.set_sample_count(5)
    driver.get_immediate_measurement()
    assert driver.get_reading_count() == 5
    drained = driver.drain_readings(2)
    assert len(drained) == 2
    assert driver.get_reading_count() == 3


def test_copy_to_nonvolatile_memory_round_trip(driver):
    """task §14.1 item 13: trigger/seed readings, copy, then read back and clear."""

    driver.set_sample_count(4)
    driver.get_immediate_measurement()
    assert driver.get_nonvolatile_reading_count() == 0

    driver.copy_readings_to_nonvolatile_memory()
    assert driver.get_nonvolatile_reading_count() == 4
    readings = driver.get_nonvolatile_readings()
    assert len(readings) == 4

    driver.clear_nonvolatile_readings()
    assert driver.get_nonvolatile_reading_count() == 0


def test_drain_nonvolatile_readings_is_destructive(driver):
    driver.set_sample_count(3)
    driver.get_immediate_measurement()
    driver.copy_readings_to_nonvolatile_memory()

    drained = driver.drain_nonvolatile_readings(max_count=2)
    assert len(drained) == 2
    assert driver.get_nonvolatile_reading_count() == 1
