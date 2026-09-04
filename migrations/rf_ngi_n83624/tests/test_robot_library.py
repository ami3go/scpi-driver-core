from __future__ import annotations

import json

import pytest

from ngi_n83624.exceptions import SafetyError
from rf_ngi_n83624.library import NGI_N83624


def make_library() -> NGI_N83624:
    library = NGI_N83624(auto_close_on_suite_end=False)
    library.open_n83624_emulator(alias="emu")
    return library


def test_emulator_connection_identify_and_measurement() -> None:
    library = make_library()
    try:
        assert library.identify_n83624() == "NGI,N83624,0,V1.00"
        library.set_emulator_channel_measurement(1, voltage_v=3.7, current_ma=125)
        result = library.measure_channel(1)
        assert result["voltage_v"] == 3.7
        assert result["current_ma"] == 125.0
        assert library.channel_voltage_should_be_within(1, 3.7, 0.01) == 3.7
    finally:
        library.close_all_n83624_connections()


def test_output_enable_requires_explicit_arming() -> None:
    library = make_library()
    try:
        library.configure_source_mode(1, 3.7, 100, output=False)
        with pytest.raises(SafetyError, match="not armed"):
            library.enable_channel_output(1)
        library.arm_channel_output(1, "ENABLE OUTPUT")
        library.enable_channel_output(1)
        library.channel_output_should_be_on(1)
        library.disable_channel_output(1)
        library.channel_output_should_be_off(1)
    finally:
        library.close_all_n83624_connections()


def test_limit_update_disarms_channel() -> None:
    library = make_library()
    try:
        library.arm_channel_output(1, "ENABLE OUTPUT")
        library.set_channel_safety_limits(1, 4.2, 500)
        with pytest.raises(AssertionError, match="not armed"):
            library.channel_output_should_be_armed(1)
    finally:
        library.close_all_n83624_connections()


def test_soc_and_sequence_accept_json() -> None:
    library = make_library()
    try:
        soc = json.dumps(
            [
                {
                    "capacity_mah": 10,
                    "voltage_v": 3.7,
                    "current_limit_ma": 100,
                    "resistance_mohm": 1,
                }
            ]
        )
        library.configure_soc_profile(1, soc, verify=False)
        sequence = json.dumps(
            [
                {
                    "voltage_v": 3.7,
                    "current_limit_ma": 100,
                    "resistance_mohm": 1,
                    "runtime_s": 1.0,
                }
            ]
        )
        library.configure_sequence_profile(1, 1, sequence, verify=False)
        commands = library.get_emulator_command_log()
        assert "SOC1:EDIT:LENGth 1" in commands
        assert "SEQuence1:EDIT:LENGth 1" in commands
    finally:
        library.close_all_n83624_connections()


def test_raw_scpi_is_guarded() -> None:
    library = NGI_N83624(auto_close_on_suite_end=False)
    library.open_n83624_emulator(alias="emu", allow_raw_scpi=False)
    try:
        with pytest.raises(SafetyError, match="Raw SCPI is disabled"):
            library.raw_scpi_query("*IDN?")
        library.enable_raw_scpi("ENABLE RAW SCPI")
        assert library.raw_scpi_query("*IDN?") == "NGI,N83624,0,V1.00"
    finally:
        library.close_all_n83624_connections()


def test_audit_log_contains_safety_actions(tmp_path) -> None:
    audit = tmp_path / "audit.jsonl"
    library = NGI_N83624(auto_close_on_suite_end=False)
    library.open_n83624_emulator(alias="emu", audit_log_path=str(audit))
    library.arm_channel_output(1, "ENABLE OUTPUT")
    library.disable_channel_output(1)
    library.close_all_n83624_connections()
    records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
    actions = {record["action"] for record in records}
    assert {"open_connection", "arm_output", "output_off", "close_connection"} <= actions
