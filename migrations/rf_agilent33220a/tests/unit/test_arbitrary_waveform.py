"""Arbitrary waveform upload/catalog/delete round-trips.

task §14.1 item 9.
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220ADeviceError, Agilent33220AValidationError


@pytest.fixture()
def driver():
    d = Agilent33220A.connect_simulated()
    yield d
    d.close()


def test_load_arbitrary_waveform_fills_volatile_slot(driver):
    """task §6 item 6: there is no custom name at upload time."""

    driver.load_arbitrary_waveform([0.0, 1.0, -1.0, 0.5])
    assert "VOLATILE" in driver.list_arbitrary_waveforms()


def test_load_arbitrary_waveform_rejects_empty_values(driver):
    with pytest.raises(Agilent33220AValidationError):
        driver.load_arbitrary_waveform([])


def test_copy_to_nonvolatile_and_select(driver):
    driver.load_arbitrary_waveform([0.0, 0.5, 1.0, 0.5])
    driver.copy_arbitrary_waveform_to_nonvolatile("MYWAVE")
    assert "MYWAVE" in driver.list_arbitrary_waveforms()

    driver.select_arbitrary_waveform("MYWAVE")
    assert driver.get_function().value == "USER"


def test_copy_to_nonvolatile_without_prior_upload_fails_clearly(driver):
    with pytest.raises(Agilent33220ADeviceError):
        driver.copy_arbitrary_waveform_to_nonvolatile("MYWAVE")


def test_delete_nonexistent_waveform_fails_clearly(driver):
    with pytest.raises(Agilent33220ADeviceError):
        driver.delete_arbitrary_waveform("DOES-NOT-EXIST")


def test_delete_all_arbitrary_waveforms(driver):
    driver.load_arbitrary_waveform([0.0, 1.0])
    driver.copy_arbitrary_waveform_to_nonvolatile("MYWAVE")
    driver.delete_all_arbitrary_waveforms()
    assert driver.list_arbitrary_waveforms() == []


def test_arbitrary_waveform_attributes(driver):
    driver.load_arbitrary_waveform([0.0, 1.0, -1.0, 1.0])
    driver.copy_arbitrary_waveform_to_nonvolatile("MYWAVE")

    attrs = driver.get_arbitrary_waveform_attributes("MYWAVE")
    assert attrs.name == "MYWAVE"
    assert attrs.points == 4
    assert attrs.peak_to_peak == pytest.approx(2.0)
