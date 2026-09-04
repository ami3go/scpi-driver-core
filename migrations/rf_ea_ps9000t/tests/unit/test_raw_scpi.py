"""Raw SCPI escape hatch guard.

task §12.1 item 10 (matching every other driver's precedent in this repository).
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.exceptions import EaPs9000TValidationError
from rf_ea_ps9000t.library import EaPs9000TLibrary


@pytest.fixture()
def driver():
    d = EaPs9000T.connect_simulated()
    yield d
    d.close()


def test_raw_write_and_query_require_enable_first(driver):
    with pytest.raises(EaPs9000TValidationError, match="disabled"):
        driver.raw_query("*IDN?")
    with pytest.raises(EaPs9000TValidationError, match="disabled"):
        driver.raw_write("VOLTage 5")


def test_enable_raw_scpi_rejects_wrong_confirmation_text(driver):
    with pytest.raises(EaPs9000TValidationError, match="confirmation"):
        driver.enable_raw_scpi("yes please")


def test_enable_raw_scpi_with_exact_text_unlocks_raw_access(driver):
    driver.enable_raw_scpi("ENABLE RAW SCPI")
    assert driver.raw_query("*IDN?").startswith("EA-Elektro-Automatik")
    driver.raw_write("VOLTage 10")
    assert driver.get_voltage() == pytest.approx(10.0)


def test_library_raw_scpi_keywords_go_through_the_same_guard():
    lib = EaPs9000TLibrary()
    lib.connect(alias="psu1", simulated=True)
    with pytest.raises(EaPs9000TValidationError, match="disabled"):
        lib.raw_scpi_query("*IDN?", alias="psu1")

    lib.enable_raw_scpi("ENABLE RAW SCPI", alias="psu1")
    assert lib.raw_scpi_query("*IDN?", alias="psu1").startswith("EA-Elektro-Automatik")
    lib.disconnect("psu1")
