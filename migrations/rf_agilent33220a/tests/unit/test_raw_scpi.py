"""Raw SCPI escape hatch guard.

task §14.1 item 6 (matching rf_ngi_n83624/rf_eresistor/rf_tbs1000c precedent).
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220AValidationError
from rf_agilent33220a.library import Agilent33220ALibrary


@pytest.fixture()
def driver():
    d = Agilent33220A.connect_simulated()
    yield d
    d.close()


def test_raw_write_and_query_require_enable_first(driver):
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.raw_query("*IDN?")
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        driver.raw_write("FREQuency 1000")


def test_enable_raw_scpi_rejects_wrong_confirmation_text(driver):
    with pytest.raises(Agilent33220AValidationError, match="confirmation"):
        driver.enable_raw_scpi("yes please")


def test_enable_raw_scpi_with_exact_text_unlocks_raw_access(driver):
    driver.enable_raw_scpi("ENABLE RAW SCPI")
    assert driver.raw_query("*IDN?").startswith("Agilent Technologies")
    driver.raw_write("FREQuency 4242")
    assert driver.get_frequency() == pytest.approx(4242.0)


def test_library_raw_scpi_keywords_go_through_the_same_guard():
    lib = Agilent33220ALibrary()
    lib.connect(alias="gen1", simulated=True)
    with pytest.raises(Agilent33220AValidationError, match="disabled"):
        lib.raw_scpi_query("*IDN?", alias="gen1")

    lib.enable_raw_scpi("ENABLE RAW SCPI", alias="gen1")
    assert lib.raw_scpi_query("*IDN?", alias="gen1").startswith("Agilent Technologies")
    lib.disconnect("gen1")
