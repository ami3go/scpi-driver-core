"""Instrument memory (MEMory subsystem) state storage round-trips.

task §14.1 item 14.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.enums import Function
from agilent34411a.exceptions import Agilent34411AValidationError


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_save_and_restore_round_trip(driver):
    driver.set_function(Function.DC_VOLTAGE)
    driver.set_range(Function.DC_VOLTAGE, 100.0)
    assert driver.is_instrument_memory_slot_valid(1) is False

    driver.save_setup_to_instrument_memory(1)
    assert driver.is_instrument_memory_slot_valid(1) is True

    driver.set_range(Function.DC_VOLTAGE, 10.0)
    driver.restore_setup_from_instrument_memory(1)
    assert driver.get_range(Function.DC_VOLTAGE) == 100.0


def test_restore_from_never_saved_slot_raises_clear_error(driver):
    """task §11: reject client-side instead of sending *RCL and letting the instrument decide."""

    with pytest.raises(Agilent34411AValidationError, match="never been saved"):
        driver.restore_setup_from_instrument_memory(3)


def test_save_and_restore_validates_slot_range(driver):
    with pytest.raises(Agilent34411AValidationError):
        driver.save_setup_to_instrument_memory(5)
    with pytest.raises(Agilent34411AValidationError):
        driver.restore_setup_from_instrument_memory(-1)


def test_catalog_and_delete(driver):
    driver.save_setup_to_instrument_memory(1)
    driver.save_setup_to_instrument_memory(2)
    assert driver.get_instrument_memory_catalog() == [1, 2]

    driver.delete_instrument_memory_slot(1)
    assert driver.get_instrument_memory_catalog() == [2]
    assert driver.is_instrument_memory_slot_valid(1) is False

    driver.delete_all_instrument_memory_slots()
    assert driver.get_instrument_memory_catalog() == []


def test_rename_and_get_name(driver):
    driver.save_setup_to_instrument_memory(1)
    driver.rename_instrument_memory_slot(1, "MY_SETUP")
    assert driver.get_instrument_memory_slot_name(1) == "MY_SETUP"


def test_power_on_state_recall(driver):
    driver.save_setup_to_instrument_memory(2)
    driver.set_power_on_state_recall(True)
    driver.set_power_on_state(2)


def test_instrument_memory_slot_count(driver):
    assert driver.get_instrument_memory_slot_count() == 5
