"""Alarm counter readback after simulator trigger hooks.

task §12.1 item 9.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_alarm_counters_start_at_zero(driver):
    counters = driver.get_alarm_counters()
    assert counters.overvoltage == 0
    assert counters.overtemperature == 0
    assert counters.overpower == 0
    assert counters.overcurrent == 0
    assert counters.power_fail == 0


def test_alarm_counters_reflect_simulator_trigger_hooks(driver):
    sim = driver.transport.simulator  # type: ignore[attr-defined]
    sim.alarm_counters.overvoltage = 2
    sim.alarm_counters.overtemperature = 1
    sim.alarm_counters.overpower = 3
    sim.alarm_counters.overcurrent = 4
    sim.alarm_counters.power_fail = 5

    counters = driver.get_alarm_counters()
    assert counters.overvoltage == 2
    assert counters.overtemperature == 1
    assert counters.overpower == 3
    assert counters.overcurrent == 4
    assert counters.power_fail == 5
