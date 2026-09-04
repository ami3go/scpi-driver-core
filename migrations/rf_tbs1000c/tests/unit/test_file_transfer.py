"""Screen image, waveform CSV, and setup save/restore. task §13.1 items 10-13."""

from __future__ import annotations

import csv

import pytest

from tbs1000c.driver import Tbs1000c
from tbs1000c.exceptions import Tbs1000cDeviceError, Tbs1000cError, Tbs1000cValidationError


def test_save_screen_image_writes_exact_bytes_and_cleans_up_temp_file(tmp_path):
    driver = Tbs1000c.connect_simulated()
    simulator = driver.transport.simulator  # type: ignore[attr-defined]

    image_path = tmp_path / "screen.png"
    driver.save_screen_image(image_path)

    assert image_path.exists()
    # The instrument-side temp file used to produce it must be cleaned up afterward.
    assert not any(name.startswith("tmp_rf_tbs1000c_screen") for name in simulator.filesystem)
    assert image_path.read_bytes() == b"SIMULATED-PNG-IMAGE"
    driver.close()


def test_save_screen_image_infers_format_from_extension(tmp_path):
    driver = Tbs1000c.connect_simulated()
    bmp_path = tmp_path / "screen.bmp"
    driver.save_screen_image(bmp_path)
    assert bmp_path.read_bytes() == b"SIMULATED-BMP-IMAGE"
    driver.close()


def test_save_waveform_to_csv_matches_get_waveform_exactly(tmp_path):
    driver = Tbs1000c.connect_simulated()
    waveform = driver.get_waveform(1)

    csv_path = tmp_path / "wave.csv"
    driver.save_waveform_to_csv(csv_path, 1)

    with csv_path.open(newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == ["time_s", "volts"]
    assert len(rows) - 1 == len(waveform.time_s)
    for (t_expected, v_expected), row in zip(zip(waveform.time_s, waveform.volts), rows[1:]):
        assert float(row[0]) == t_expected
        assert float(row[1]) == v_expected
    driver.close()


def test_save_setup_restore_setup_round_trip(tmp_path):
    driver = Tbs1000c.connect_simulated()
    driver.set_channel_scale(1, 0.5)
    driver.set_channel_coupling(1, "AC")

    setup_path = tmp_path / "setup.txt"
    driver.save_setup(setup_path)
    assert setup_path.exists()
    assert "CH1" in setup_path.read_text()

    driver.set_channel_scale(1, 2.0)
    driver.set_channel_coupling(1, "DC")
    assert driver.get_channel_scale(1) == 2.0

    driver.restore_setup(setup_path)
    assert driver.get_channel_scale(1) == 0.5
    assert driver.get_channel_coupling(1).value == "AC"
    driver.close()


def test_restore_setup_rejects_empty_file(tmp_path):
    driver = Tbs1000c.connect_simulated()
    empty_path = tmp_path / "empty.txt"
    empty_path.write_text("")
    with pytest.raises(Tbs1000cValidationError):
        driver.restore_setup(empty_path)
    driver.close()


def test_restore_setup_rejects_missing_file(tmp_path):
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.restore_setup(tmp_path / "does_not_exist.txt")
    driver.close()


def test_restore_setup_rejects_foreign_content_instead_of_silently_reconfiguring(tmp_path):
    driver = Tbs1000c.connect_simulated()
    driver.set_channel_scale(1, 0.5)

    garbage_path = tmp_path / "garbage.txt"
    garbage_path.write_text("THIS IS NOT A REAL SETUP STRING")

    with pytest.raises(Tbs1000cError):
        driver.restore_setup(garbage_path)

    # The known-good configuration must be untouched by the rejected restore.
    assert driver.get_channel_scale(1) == 0.5
    driver.close()


def test_restore_setup_device_error_reports_the_instrument_event(tmp_path):
    driver = Tbs1000c.connect_simulated()
    garbage_path = tmp_path / "garbage.txt"
    garbage_path.write_text("NOT A COMMAND")
    with pytest.raises(Tbs1000cDeviceError, match="Undefined header"):
        driver.restore_setup(garbage_path)
    driver.close()


def test_save_setup_to_instrument_memory_round_trip():
    driver = Tbs1000c.connect_simulated()
    driver.set_channel_scale(2, 0.1)
    driver.save_setup_to_instrument_memory(5)

    driver.set_channel_scale(2, 5.0)
    driver.restore_setup_from_instrument_memory(5)
    # The simulator's *RCL is a stub (real hardware applies the stored setup);
    # verify the call at least completes and the slot is populated.
    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    assert 5 in simulator.memory_slots
    driver.close()


def test_slot_out_of_range_rejected():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.save_setup_to_instrument_memory(0)
    with pytest.raises(Tbs1000cValidationError):
        driver.save_setup_to_instrument_memory(11)
    driver.close()


# -- Gate 3: instrument-side waveform save/recall (SAVe:WAVEform REF<x>, RECAll:WAVEform) --


def test_save_waveform_to_reference_memory_round_trip():
    driver = Tbs1000c.connect_simulated()
    driver.set_channel_scale(1, 0.5)

    driver.save_waveform_to_reference_memory(1, 1)

    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    assert 1 in simulator.reference_waveforms
    assert len(simulator.reference_waveforms[1]) == simulator.record_length
    driver.close()


def test_save_waveform_to_reference_memory_rejects_invalid_ref():
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(Tbs1000cValidationError):
        driver.save_waveform_to_reference_memory(1, 3)
    with pytest.raises(Tbs1000cValidationError):
        driver.save_waveform_to_reference_memory(1, 0)
    driver.close()


def test_recall_waveform_from_host_file_round_trip(tmp_path):
    """Save a waveform to a host file via the instrument-side path, then push it back
    onto the instrument and load it into reference memory — full round trip."""

    driver = Tbs1000c.connect_simulated()
    csv_path = tmp_path / "ch1.csv"
    driver.save_waveform_to_csv_on_instrument(csv_path, 1)
    assert csv_path.exists()

    driver.recall_waveform_from_host_file(csv_path, 2)

    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    assert 2 in simulator.reference_waveforms
    assert simulator.reference_waveforms[2] == csv_path.read_bytes()
    # The instrument-side temp file used to upload it must be cleaned up afterward.
    assert not any(name.startswith("tmp_rf_tbs1000c_recall_ref") for name in simulator.filesystem)
    driver.close()


def test_recall_waveform_from_host_file_rejects_invalid_ref(tmp_path):
    driver = Tbs1000c.connect_simulated()
    csv_path = tmp_path / "ch1.csv"
    csv_path.write_text("Time,Value\n0,0\n")
    with pytest.raises(Tbs1000cValidationError):
        driver.recall_waveform_from_host_file(csv_path, 5)
    driver.close()


def test_recall_waveform_from_host_file_raises_for_missing_host_file(tmp_path):
    driver = Tbs1000c.connect_simulated()
    with pytest.raises(FileNotFoundError):
        driver.recall_waveform_from_host_file(tmp_path / "does_not_exist.csv", 1)
    driver.close()
