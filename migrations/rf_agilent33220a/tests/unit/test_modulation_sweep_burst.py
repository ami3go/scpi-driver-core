"""Modulation, sweep+marker, burst, and trigger round-trips.

task §14.1 items 14 (marker) plus the general modulation/sweep/burst surface
that Configure Output's neighbors are built on.
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220AValidationError


@pytest.fixture()
def driver():
    d = Agilent33220A.connect_simulated()
    yield d
    d.close()


def test_amplitude_modulation_round_trip(driver):
    driver.configure_amplitude_modulation("SIN", 200.0, 50.0, "INT")
    driver.enable_amplitude_modulation()
    driver.disable_amplitude_modulation()


def test_frequency_modulation_round_trip(driver):
    driver.configure_frequency_modulation("TRI", 300.0, 1000.0, "INT")
    driver.enable_frequency_modulation()
    driver.disable_frequency_modulation()


def test_phase_modulation_round_trip(driver):
    driver.configure_phase_modulation("SQU", 400.0, 90.0, "INT")
    driver.enable_phase_modulation()
    driver.disable_phase_modulation()


def test_frequency_shift_keying_round_trip(driver):
    driver.configure_frequency_shift_keying(5000.0, 50.0, "INT")
    driver.enable_frequency_shift_keying()
    driver.disable_frequency_shift_keying()


def test_pulse_width_modulation_round_trip(driver):
    driver.configure_pulse_width_modulation("RAMP", 100.0, 1e-5, "INT")
    driver.enable_pulse_width_modulation()
    driver.disable_pulse_width_modulation()


def test_frequency_sweep_and_marker_round_trip(driver):
    """task §14.1 item 14."""

    driver.configure_frequency_sweep(100.0, 10_000.0, "LIN", 2.0)
    driver.enable_sweep()
    assert driver.transport.simulator.sweep.state is True  # type: ignore[attr-defined]

    driver.set_sweep_marker_frequency(5000.0)
    assert driver.get_sweep_marker_frequency() == 5000.0

    driver.enable_sweep_marker()
    assert driver.transport.simulator.sweep.marker_enabled is True  # type: ignore[attr-defined]
    driver.disable_sweep_marker()
    assert driver.transport.simulator.sweep.marker_enabled is False  # type: ignore[attr-defined]

    driver.disable_sweep()


def test_burst_round_trip(driver):
    driver.configure_burst("TRIG", 5, period=0.01, phase_degrees=45.0)
    driver.enable_burst()
    driver.set_burst_gate_polarity("INV")
    driver.disable_burst()


def test_pulse_round_trip(driver):
    driver.configure_pulse(period=1e-3, duty_cycle=25.0, transition=1e-7)
    driver.configure_pulse(width=2e-4)


def test_trigger_now_requires_bus_source(driver):
    with pytest.raises(Agilent33220AValidationError, match="BUS"):
        driver.trigger_now()

    driver.set_trigger_source("BUS")
    driver.trigger_now()  # now valid, must not raise


def test_trigger_source_and_slope_round_trip(driver):
    driver.set_trigger_source("EXT")
    assert driver.get_trigger_source().value == "EXT"
    driver.set_trigger_slope("NEG")
    assert driver.get_trigger_slope().value == "NEG"
    settings = driver.get_trigger_settings()
    assert settings.source == "EXT"
    assert settings.slope == "NEG"
