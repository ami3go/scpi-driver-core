"""Overload/out-of-range measurements raise rather than return a fabricated value.

task §13.1 item 4.
"""

from __future__ import annotations

import pytest

from tbs1000c.driver import Tbs1000c
from tbs1000c.exceptions import Tbs1000cDeviceError, Tbs1000cValidationError


def test_normal_measurement_returns_a_real_value():
    driver = Tbs1000c.connect_simulated()
    value = driver.get_immediate_measurement("FREQuency", 1)
    assert value == pytest.approx(1000.0)
    driver.close()


def test_overloaded_measurement_raises_not_fabricates():
    driver = Tbs1000c.connect_simulated()
    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    simulator.force_next_measurement_overload(True)

    with pytest.raises(Tbs1000cDeviceError, match="overload"):
        driver.get_immediate_measurement("AMPlitude", 1)

    simulator.force_next_measurement_overload(False)
    driver.close()


def test_invalid_measurement_type_rejected():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(ValueError):
        driver.get_immediate_measurement("NOT_A_REAL_TYPE", 1)
    driver.close()


def test_measurement_should_be_within_passes_and_fails_correctly():
    from rf_tbs1000c.library import Tbs1000cLibrary

    lib = Tbs1000cLibrary()
    lib.connect(alias="scope", simulated=True)

    lib.measurement_should_be_within("FREQuency", 1, 900.0, 1100.0, alias="scope")

    with pytest.raises(AssertionError):
        lib.measurement_should_be_within("FREQuency", 1, 1.0, 2.0, alias="scope")

    with pytest.raises(Tbs1000cValidationError):
        lib.measurement_should_be_within("FREQuency", 1, 2000.0, 1.0, alias="scope")

    lib.disconnect("scope")
