import pytest

from KeysightN6700Library.library import KeysightN6700Library, _as_float, _as_seconds


def test_engineering_value_conversion():
    assert _as_float("12V") == pytest.approx(12.0)
    assert _as_float("500mA") == pytest.approx(0.5)
    assert _as_float("10uA") == pytest.approx(10e-6)
    assert _as_float("2.2k") == pytest.approx(2200.0)
    assert _as_float("1M") == pytest.approx(1e6)


def test_time_conversion():
    assert _as_seconds("500ms") == pytest.approx(0.5)
    assert _as_seconds("2min") == pytest.approx(120.0)


def test_simulated_power_supply_workflow():
    lib = KeysightN6700Library()
    lib.connect_to_simulated_n6700()
    result = lib.configure_n6700_power_supply_channel(1, "5V", "1A", output=True)
    assert result["output_enabled"] is True
    assert lib.measure_n6700_voltage(1) == pytest.approx(5.0)
    assert lib.measure_n6700_current(1) == pytest.approx(0.5)
    lib.n6700_power_should_be(1, "2.5W", "1mW")
    lib.disconnect_all_n6700()


def test_named_sessions_are_independent():
    lib = KeysightN6700Library()
    lib.connect_to_simulated_n6700("a")
    lib.connect_to_simulated_n6700("b")
    lib.set_n6700_voltage(1, 3.3, alias="a")
    lib.set_n6700_voltage(1, 12, alias="b")
    assert lib.get_n6700_voltage_setpoint(1, "a") == pytest.approx(3.3)
    assert lib.get_n6700_voltage_setpoint(1, "b") == pytest.approx(12)
    lib.disconnect_all_n6700()


def test_load_and_smu_workflows():
    lib = KeysightN6700Library()
    lib.connect_to_simulated_n6700()
    lib.configure_n6700_smu_current_priority(2, "100mA", "3.3V")
    assert lib.get_n6700_smu_mode(2) == "current"
    lib.configure_n6700_load_cc(3, "250mA", input_on=True)
    assert lib.get_n6700_load_input_state(3) is True
    assert lib.get_n6700_load_level(3, "cc") == pytest.approx(0.25)
    lib.disconnect_all_n6700()


def test_disconnect_performs_safe_shutdown():
    lib = KeysightN6700Library(auto_shutdown=True)
    lib.connect_to_simulated_n6700()
    lib.configure_n6700_power_supply_channel(1, 5, 1, output=True)
    instrument = lib._instrument()
    lib.disconnect_all_n6700()
    assert instrument.power_supply(1).get_output() is False


def test_explicit_usb_connection_keyword_delegates_to_usb_transport(monkeypatch):
    lib = KeysightN6700Library()
    captured = {}

    def fake_connect_to_n6700(**kwargs):
        captured.update(kwargs)
        return kwargs["alias"]

    monkeypatch.setattr(lib, "connect_to_n6700", fake_connect_to_n6700)
    alias = lib.connect_to_n6700_via_usb(
        "USB0::0x0957::0x0907::MY43014421::INSTR",
        alias="n6775a_usb",
        audit_log_path="trace.jsonl",
    )

    assert alias == "n6775a_usb"
    assert captured["resource"] == "USB0::0x0957::0x0907::MY43014421::INSTR"
    assert captured["connection_type"] == "usb"
    assert captured["audit_log_path"] == "trace.jsonl"
