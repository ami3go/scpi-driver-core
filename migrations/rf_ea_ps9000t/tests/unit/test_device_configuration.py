"""Device configuration round-trips (PST-applicable subset only).

task §12.1 items 8, 9, 13.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.enums import AlarmAction, OutputRestoreMode, PowerStageAfterRemote
from ea_ps9000t.exceptions import EaPs9000TValidationError


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_power_stage_after_remote_round_trip(driver):
    driver.set_power_stage_after_remote(PowerStageAfterRemote.OFF)
    assert driver.get_power_stage_after_remote() == PowerStageAfterRemote.OFF


def test_output_restore_mode_round_trip(driver):
    driver.set_output_restore_mode(OutputRestoreMode.OFF)
    assert driver.get_output_restore_mode() == OutputRestoreMode.OFF


def test_user_text_round_trip(driver):
    driver.set_user_text("bench 3")
    assert driver.get_user_text() == "bench 3"


def test_user_text_rejects_too_long_string(driver):
    with pytest.raises(EaPs9000TValidationError):
        driver.set_user_text("x" * 41)


def test_communication_timeout_round_trip_no_interface_gating(driver):
    """task §12.1 item 13: a plain pass-through keyword, no client-side interface-type
    gating, since the driver has no reliable way to know the active transport type."""

    driver.set_communication_timeout(100)
    assert driver.get_communication_timeout() == 100


def test_communication_timeout_validates_range(driver):
    with pytest.raises(EaPs9000TValidationError):
        driver.set_communication_timeout(4)
    with pytest.raises(EaPs9000TValidationError):
        driver.set_communication_timeout(65536)


def test_alarm_actions_round_trip(driver):
    driver.set_power_fail_alarm_action(AlarmAction.OFF)
    assert driver.get_power_fail_alarm_action() == AlarmAction.OFF
    driver.set_overtemperature_alarm_action(AlarmAction.OFF)
    assert driver.get_overtemperature_alarm_action() == AlarmAction.OFF
