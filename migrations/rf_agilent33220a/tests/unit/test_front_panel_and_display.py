"""Front-panel lock and display keywords.

task §14.1 item 13.
"""

from __future__ import annotations

from agilent33220a.driver import Agilent33220A


def test_front_panel_lock_round_trip_without_prior_state_assumption():
    """Is Front Panel Locked reflects current state without requiring a
    prior explicit lock/unlock call in the same test."""

    driver = Agilent33220A.connect_simulated()
    assert driver.is_front_panel_locked() is False

    driver.lock_front_panel()
    assert driver.is_front_panel_locked() is True

    driver.unlock_front_panel()
    assert driver.is_front_panel_locked() is False
    driver.close()


def test_display_text_and_on_off_round_trip():
    driver = Agilent33220A.connect_simulated()
    driver.set_display_text("STEP 3 OF 5")
    driver.clear_display_text()
    driver.disable_display()
    driver.enable_display()
    driver.close()
