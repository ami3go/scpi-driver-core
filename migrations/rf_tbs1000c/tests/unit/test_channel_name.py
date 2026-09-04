"""Channel naming: 30-character limit enforced client-side; empty string clears the label.

task §13.1 item 9.
"""

from __future__ import annotations

import pytest

from tbs1000c.driver import Tbs1000c
from tbs1000c.exceptions import Tbs1000cValidationError


def test_channel_name_round_trips():
    driver = Tbs1000c.connect_simulated()
    driver.set_channel_name(1, "ICCDATA")
    assert driver.get_channel_name(1) == "ICCDATA"
    driver.close()


def test_channel_name_over_30_characters_rejected_before_any_device_io():
    driver = Tbs1000c.connect_simulated()
    simulator = driver.transport.simulator  # type: ignore[attr-defined]

    too_long = "x" * 31
    with pytest.raises(Tbs1000cValidationError, match="30"):
        driver.set_channel_name(1, too_long)

    # Rejected before it ever reached the instrument: the label is unchanged.
    assert simulator.channels["1"]["label"] == ""
    driver.close()


def test_channel_name_exactly_30_characters_is_accepted():
    driver = Tbs1000c.connect_simulated()
    exactly_30 = "x" * 30
    driver.set_channel_name(1, exactly_30)
    assert driver.get_channel_name(1) == exactly_30
    driver.close()


def test_empty_channel_name_clears_label():
    driver = Tbs1000c.connect_simulated()
    driver.set_channel_name(1, "SOMETHING")
    assert driver.get_channel_name(1) == "SOMETHING"

    driver.set_channel_name(1, "")
    assert driver.get_channel_name(1) == ""

    driver.set_channel_name(1, None)
    assert driver.get_channel_name(1) == ""
    driver.close()


def test_invalid_channel_number_rejected():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.set_channel_name(3, "x")
    driver.close()
