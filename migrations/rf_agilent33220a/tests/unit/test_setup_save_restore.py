"""Setup save/restore round-trips: host file and instrument memory.

task §14.1 items 10, 11, 12.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220AValidationError


@pytest.fixture()
def driver():
    d = Agilent33220A.connect_simulated()
    yield d
    d.close()


def test_save_and_restore_setup_round_trip(driver, tmp_path: Path):
    """task §14.1 item 10 (mirrors rf_tbs1000c test #12)."""

    driver.set_function("SQU")
    driver.set_frequency(2500.0)
    driver.set_amplitude(3.0)
    driver.set_offset(0.5)

    setup_path = tmp_path / "setup.txt"
    driver.save_setup(setup_path)
    assert setup_path.is_file()
    assert "FUNCtion SQU" in setup_path.read_text()

    # Mutate state, then restore and confirm it comes back.
    driver.set_function("SIN")
    driver.set_frequency(100.0)
    driver.restore_setup(setup_path)

    assert driver.get_function().value == "SQU"
    assert driver.get_frequency() == pytest.approx(2500.0)
    assert driver.get_amplitude() == pytest.approx(3.0)
    assert driver.get_offset() == pytest.approx(0.5)


def test_restore_setup_missing_file_fails_clearly(driver, tmp_path: Path):
    """task §14.1 item 11 (mirrors rf_tbs1000c test #13)."""

    with pytest.raises(Agilent33220AValidationError, match="not found"):
        driver.restore_setup(tmp_path / "does-not-exist.txt")


def test_restore_setup_empty_file_fails_clearly(driver, tmp_path: Path):
    empty_path = tmp_path / "empty.txt"
    empty_path.write_text("")
    with pytest.raises(Agilent33220AValidationError, match="empty"):
        driver.restore_setup(empty_path)


def test_save_and_restore_setup_from_instrument_memory_round_trip(driver):
    """task §14.1 item 12."""

    driver.set_frequency(7777.0)
    driver.save_setup_to_instrument_memory(1)

    driver.set_frequency(100.0)
    driver.restore_setup_from_instrument_memory(1)
    assert driver.get_frequency() == pytest.approx(7777.0)


def test_restore_from_never_saved_slot_raises_clear_error(driver):
    with pytest.raises(Agilent33220AValidationError, match="never been saved"):
        driver.restore_setup_from_instrument_memory(4)


def test_restore_setup_from_instrument_memory_validates_slot_range(driver):
    with pytest.raises(Agilent33220AValidationError):
        driver.restore_setup_from_instrument_memory(5)


def test_restore_factory_setup_resets_output(driver):
    driver.set_frequency(9999.0)
    driver.restore_factory_setup()
    assert driver.get_frequency() != 9999.0
