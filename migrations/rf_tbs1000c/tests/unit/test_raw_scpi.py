"""Raw SCPI escape hatch requires the exact confirmation text. task §13.1 item 6."""

from __future__ import annotations

import pytest

from tbs1000c.driver import Tbs1000c
from tbs1000c.exceptions import Tbs1000cValidationError


def test_raw_query_blocked_without_confirmation():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.raw_query("*IDN?")
    driver.close()


def test_raw_write_blocked_without_confirmation():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.raw_write("*CLS")
    driver.close()


def test_wrong_confirmation_text_rejected():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.enable_raw_scpi("enable raw scpi")  # wrong case, must be exact
    with pytest.raises(Tbs1000cValidationError):
        driver.enable_raw_scpi("YES")
    driver.close()


def test_exact_confirmation_enables_raw_scpi():
    driver = Tbs1000c.connect_simulated()
    driver.enable_raw_scpi("ENABLE RAW SCPI")
    result = driver.raw_query("*IDN?")
    assert "TEKTRONIX" in result
    driver.raw_write("*CLS")
    driver.close()
