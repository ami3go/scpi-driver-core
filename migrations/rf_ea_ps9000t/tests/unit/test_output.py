"""Output enable/disable round-trip, and rejection while remote control is not held.

task §12.1 item 6.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.exceptions import EaPs9000TDeviceError


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_output_enable_disable_round_trip(driver):
    assert driver.is_output_enabled() is False
    driver.enable_output()
    assert driver.is_output_enabled() is True
    driver.disable_output()
    assert driver.is_output_enabled() is False


def test_command_while_not_remote_raises_typed_error(driver):
    """task §12.1 item 6: reflects the device's own -201 'Invalid while in local'."""

    driver.release_remote_control()
    with pytest.raises(EaPs9000TDeviceError, match="Invalid while in local"):
        driver.enable_output()
    driver.acquire_remote_control()  # restore for fixture teardown
