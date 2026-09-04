"""The core safety behaviors this driver is designed around.

task §14.1 items 2, 3, 4, 5.
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220ADeviceError, Agilent33220ASafetyError


def test_configure_output_does_not_enable_output_by_default():
    """task §6 item 1: APPLy silently enables the output as a documented
    side effect; Configure Output must restore the prior (disabled) state
    unless enable_output=True is explicitly passed."""

    driver = Agilent33220A.connect_simulated()
    assert driver.is_output_enabled() is False

    driver.configure_output("SIN", 1000.0, 1.0, 0.0)
    assert driver.is_output_enabled() is False

    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    assert simulator.apply_calls == 1  # APPLy really was used, just contained

    driver.close()


def test_configure_output_honors_explicit_enable_output():
    driver = Agilent33220A.connect_simulated()
    driver.configure_output("SIN", 1000.0, 1.0, 0.0, enable_output=True)
    assert driver.is_output_enabled() is True
    driver.close()


def test_configure_output_preserves_prior_enabled_state():
    driver = Agilent33220A.connect_simulated()
    driver.enable_output()
    driver.configure_output("SQU", 2000.0, 1.0, 0.0)
    assert driver.is_output_enabled() is True
    driver.close()


def test_enable_disable_output_are_explicit_and_side_effect_free():
    """task §6 item 2: no other keyword changes output-enabled state as a
    side effect once Configure Output has restored it."""

    driver = Agilent33220A.connect_simulated()
    driver.set_function("SIN")
    driver.set_frequency(500.0)
    driver.set_amplitude(1.0)
    assert driver.is_output_enabled() is False

    driver.enable_output()
    assert driver.is_output_enabled() is True
    driver.disable_output()
    assert driver.is_output_enabled() is False
    driver.close()


def test_amplitude_validation_rejects_limit_violation_before_device_io():
    """task §6 item 4: Vpp < 2*(Vmax-|Voffset|), Vmax=10V in the simulator."""

    driver = Agilent33220A.connect_simulated()
    with pytest.raises(Agilent33220ASafetyError):
        driver.set_amplitude(25.0)
    # Rejected before any device I/O: amplitude on the instrument is unchanged.
    assert driver.get_amplitude() != 25.0
    driver.close()


def test_offset_validation_rejects_limit_violation_before_device_io():
    driver = Agilent33220A.connect_simulated()
    driver.set_amplitude(8.0)
    with pytest.raises(Agilent33220ASafetyError):
        driver.set_offset(9.0)  # 8 < 2*(10-9)=2 is false -> violates constraint
    assert driver.get_offset() != 9.0
    driver.close()


def test_amplitude_validation_allows_values_within_the_documented_limit():
    driver = Agilent33220A.connect_simulated()
    driver.set_offset(1.0)
    driver.set_amplitude(2.0)  # 2 < 2*(10-1)=18 -> fine
    assert driver.get_amplitude() == 2.0
    driver.close()


def test_settings_conflict_on_function_change_raises_typed_error_naming_adjusted_value():
    """task §6 item 5: a function change that forces the instrument to adjust
    frequency/amplitude must surface as a typed error naming the actual
    adjusted values, not be silently swallowed."""

    driver = Agilent33220A.connect_simulated()
    driver.set_frequency(15_000_000.0)
    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    simulator.settings_conflict_next_function_change = True

    with pytest.raises(Agilent33220ADeviceError, match="Settings conflict"):
        driver.set_function("PULS")

    # The instrument's own adjustment is reflected, not reverted behind our back.
    assert driver.get_frequency() <= 2.0e5
    driver.close()
