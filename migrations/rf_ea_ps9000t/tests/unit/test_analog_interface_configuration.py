"""Analog interface configuration round-trips (Gate 3 extension —
SYSTem:CONFig:ANAlog:REFerence/:REMSB:*).

Confirmed present for the PST series specifically, from the EA/Intepro
"Programming Guide ModBus & SCPI" (Doc ID PGMBEN, Rev. 17), task §2/§9.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.enums import AnalogRemsbAction, AnalogRemsbLevel
from ea_ps9000t.exceptions import EaPs9000TDeviceError, EaPs9000TValidationError


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_reference_range_round_trip(driver):
    assert driver.get_analog_reference_range() == 10  # factory default
    driver.set_analog_reference_range(5)
    assert driver.get_analog_reference_range() == 5
    driver.set_analog_reference_range(10)
    assert driver.get_analog_reference_range() == 10


def test_reference_range_rejects_invalid_value(driver):
    for bad in (0, 7, -5, 15):
        with pytest.raises(EaPs9000TValidationError):
            driver.set_analog_reference_range(bad)


def test_remsb_level_round_trip(driver):
    assert driver.get_analog_remsb_level() == AnalogRemsbLevel.NORMAL  # factory default
    driver.set_analog_remsb_level(AnalogRemsbLevel.INVERTED)
    assert driver.get_analog_remsb_level() == AnalogRemsbLevel.INVERTED
    driver.set_analog_remsb_level("NORMAL")
    assert driver.get_analog_remsb_level() == AnalogRemsbLevel.NORMAL


def test_remsb_action_round_trip(driver):
    assert driver.get_analog_remsb_action() == AnalogRemsbAction.OFF  # factory default
    driver.set_analog_remsb_action(AnalogRemsbAction.AUTO)
    assert driver.get_analog_remsb_action() == AnalogRemsbAction.AUTO
    driver.set_analog_remsb_action("OFF")
    assert driver.get_analog_remsb_action() == AnalogRemsbAction.OFF


def test_analog_config_write_while_not_remote_raises_typed_error(driver):
    """Every mutating analog-interface command is rejected the same way as any
    other mutating command on this instrument family when remote control is
    not held."""

    driver.release_remote_control()
    with pytest.raises(EaPs9000TDeviceError, match="Invalid while in local"):
        driver.set_analog_reference_range(5)
    with pytest.raises(EaPs9000TDeviceError, match="Invalid while in local"):
        driver.set_analog_remsb_level(AnalogRemsbLevel.INVERTED)
    with pytest.raises(EaPs9000TDeviceError, match="Invalid while in local"):
        driver.set_analog_remsb_action(AnalogRemsbAction.AUTO)
    driver.acquire_remote_control()  # restore for fixture teardown
