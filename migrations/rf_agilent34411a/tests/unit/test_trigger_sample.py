"""Trigger source/level/slope and sample count/pre-trigger round-trips.

task §14.1 items 8, 9.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.enums import Function, TriggerSlope, TriggerSource
from agilent34411a.exceptions import Agilent34411AValidationError


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_trigger_source_round_trip(driver):
    driver.set_trigger_source(TriggerSource.EXTERNAL)
    assert driver.get_trigger_source() == TriggerSource.EXTERNAL


def test_internal_trigger_source_rejected_for_ineligible_function(driver):
    """task §14.1 item 8: capacitance/frequency/period/temperature don't support level triggering."""

    driver.set_function(Function.CAPACITANCE)
    with pytest.raises(Agilent34411AValidationError):
        driver.set_trigger_source(TriggerSource.INTERNAL)

    driver.set_function(Function.TEMPERATURE)
    with pytest.raises(Agilent34411AValidationError):
        driver.set_trigger_source(TriggerSource.INTERNAL)


def test_internal_trigger_source_accepted_for_eligible_function(driver):
    driver.set_function(Function.DC_VOLTAGE)
    driver.set_trigger_source(TriggerSource.INTERNAL)
    assert driver.get_trigger_source() == TriggerSource.INTERNAL
    driver.set_trigger_level(2.5)
    assert driver.get_trigger_level() == pytest.approx(2.5)
    driver.set_trigger_slope(TriggerSlope.NEGATIVE)
    assert driver.get_trigger_slope() == TriggerSlope.NEGATIVE


def test_trigger_now_requires_bus_source(driver):
    with pytest.raises(Agilent34411AValidationError, match="BUS"):
        driver.trigger_now()

    driver.set_trigger_source(TriggerSource.BUS)
    driver.trigger_now()  # now valid, must not raise


def test_pretrigger_sample_count_rejects_value_not_less_than_sample_count(driver):
    """task §14.1 item 9."""

    driver.set_sample_count(10)
    with pytest.raises(Agilent34411AValidationError):
        driver.set_pretrigger_sample_count(10)
    with pytest.raises(Agilent34411AValidationError):
        driver.set_pretrigger_sample_count(15)
    driver.set_pretrigger_sample_count(5)  # now valid


def test_trigger_settings_snapshot(driver):
    driver.set_trigger_source(TriggerSource.EXTERNAL)
    driver.set_sample_count(3)
    settings = driver.get_trigger_settings()
    assert settings.source == "EXT"
    assert settings.sample_count == 3.0
