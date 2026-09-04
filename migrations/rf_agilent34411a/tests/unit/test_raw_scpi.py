"""Raw SCPI escape hatch guard.

task §14.1 item 10 (matching rf_ngi_n83624/rf_eresistor/rf_tbs1000c/rf_agilent33220a precedent).
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.exceptions import Agilent34411AValidationError
from rf_agilent34411a.library import Agilent34411ALibrary


@pytest.fixture()
def driver():
    d = Agilent34411A.connect_simulated()
    yield d
    d.close()


def test_raw_write_and_query_require_enable_first(driver):
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.raw_query("*IDN?")
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        driver.raw_write("VOLTage:RANGe 10")


def test_enable_raw_scpi_rejects_wrong_confirmation_text(driver):
    with pytest.raises(Agilent34411AValidationError, match="confirmation"):
        driver.enable_raw_scpi("yes please")


def test_enable_raw_scpi_with_exact_text_unlocks_raw_access(driver):
    driver.enable_raw_scpi("ENABLE RAW SCPI")
    assert driver.raw_query("*IDN?").startswith("Agilent Technologies")
    driver.raw_write("VOLTage:RANGe 100")
    assert driver.get_range("VOLT") == 100.0


def test_library_raw_scpi_keywords_go_through_the_same_guard():
    lib = Agilent34411ALibrary()
    lib.connect(alias="dmm1", simulated=True)
    with pytest.raises(Agilent34411AValidationError, match="disabled"):
        lib.raw_scpi_query("*IDN?", alias="dmm1")

    lib.enable_raw_scpi("ENABLE RAW SCPI", alias="dmm1")
    assert lib.raw_scpi_query("*IDN?", alias="dmm1").startswith("Agilent Technologies")
    lib.disconnect("dmm1")
