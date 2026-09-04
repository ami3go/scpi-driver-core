import pytest

from keysight_n6700 import (
    N6700,
    ElectronicLoadChannel,
    PowerSupplyChannel,
    SMUChannel,
    UnsupportedFeatureError,
)
from keysight_n6700.capabilities import classify_module
from keysight_n6700.simulator import SimN6700Instrument
from keysight_n6700.transport import SimulatedTransport


def make_inst():
    return N6700(SimulatedTransport(SimN6700Instrument()))


def test_discovery_and_channel_types():
    with make_inst() as inst:
        assert inst.channel_count() == 4
        assert isinstance(inst.power_supply(1), PowerSupplyChannel)
        assert isinstance(inst.smu(2), SMUChannel)
        assert isinstance(inst.load(3), ElectronicLoadChannel)


def test_power_supply_config_does_not_enable_by_default():
    with make_inst() as inst:
        ps = inst.power_supply(1)
        ps.set_voltage_setpoint(5.0)
        ps.set_current_limit(1.0)
        assert ps.get_output() is False
        ps.output_on()
        assert ps.get_output() is True
        ps.output_off()


def test_smu_mode_and_config():
    with make_inst() as inst:
        smu = inst.smu(2)
        smu.set_smu_mode("current")
        assert smu.get_smu_mode() == "current"
        smu.configure_voltage_priority(1.2, 0.2, output=False)
        assert smu.get_output() is False


def test_sim_load_and_unsupported_policy():
    with make_inst() as inst:
        load = inst.load(3)
        load.set_load_mode("cc")
        load.set_load_current(0.1)
        assert load.get_load_mode() == "cc"
        assert load.get_input() is False
        load.input_on()
        assert load.get_input() is True
    caps = classify_module("N6799X")
    assert caps.module_type == "unknown"


def test_wrong_channel_type_raises():
    with make_inst() as inst:
        with pytest.raises(UnsupportedFeatureError):
            inst.load(1)
        with pytest.raises(UnsupportedFeatureError):
            inst.smu(1)


def test_measurement_power_source():
    with make_inst() as inst:
        meas = inst.power_supply(1).measure()
        assert meas.power_source in {"instrument", "calculated", "unavailable"}


def test_shutdown_all_attempts_all():
    with make_inst() as inst:
        inst.power_supply(1).output_on()
        inst.smu(2).output_on()
        inst.load(3).input_on()
        result = inst.shutdown_all()
        assert len(result.results) == 4
        assert not inst.power_supply(1).get_output()
        assert not inst.smu(2).get_output()
        assert not inst.load(3).get_input()


def test_safe_clear_protection_keeps_output_off():
    with make_inst() as inst:
        ps = inst.power_supply(1)
        ps.output_on()
        result = ps.clear_protection()
        assert result.output_state_before is True
        assert result.output_state_after is False
        assert result.restored_output is False


def test_transport_clear_capability():
    with make_inst() as inst:
        assert inst.transport.supports_clear is True
        inst.transport.clear()


def test_protocol_audit_trace_records_write_query_and_response(tmp_path):
    trace = tmp_path / "protocol_trace.jsonl"
    with N6700(
        SimulatedTransport(SimN6700Instrument(models={1: "N6775A"})),
        audit_log_path=trace,
    ) as inst:
        inst.power_supply(1).set_voltage_setpoint(1.25)
        assert inst.power_supply(1).get_voltage_setpoint() == pytest.approx(1.25)

    lines = trace.read_text(encoding="utf-8").splitlines()
    assert any('"operation": "write"' in line and '"command": "VOLT 1.25,(@1)"' in line for line in lines)
    assert any(
        '"operation": "query"' in line
        and '"command": "VOLT? (@1)"' in line
        and '"response": "1.25"' in line
        for line in lines
    )


def test_ocp_uses_manual_defined_state_header_and_round_trips(tmp_path):
    trace = tmp_path / "ocp_trace.jsonl"
    with N6700(
        SimulatedTransport(SimN6700Instrument(models={1: "N6775A"})),
        audit_log_path=trace,
    ) as inst:
        ps = inst.power_supply(1)
        ps.set_ocp(True)
        assert ps.get_ocp() is True
        ps.set_ocp(False)
        assert ps.get_ocp() is False

    text = trace.read_text(encoding="utf-8")
    assert '"command": "CURR:PROT:STAT ON,(@1)"' in text
    assert '"command": "CURR:PROT:STAT? (@1)"' in text
    assert '"command": "CURR:PROT:STAT OFF,(@1)"' in text
    assert '"command": "CURR:PROT? (@1)"' not in text


def test_protection_status_uses_questionable_condition_and_decodes_bits(tmp_path):
    simulator = SimN6700Instrument(models={1: "N6775A"})
    simulator.channels[1].questionable_status = 1 | 2 | 16 | 512
    trace = tmp_path / "protection_trace.jsonl"
    with N6700(SimulatedTransport(simulator), audit_log_path=trace) as inst:
        status = inst.power_supply(1).get_protection_status()

    assert status.active is True
    assert status.over_voltage is True
    assert status.over_current is True
    assert status.over_temperature is True
    assert status.inhibit is True
    assert status.power_fail is False
    assert status.power_limit is False
    assert status.raw_status == 531
    text = trace.read_text(encoding="utf-8")
    assert '"command": "STAT:QUES:COND? (@1)"' in text
    assert '"command": "OUTP:PROT? (@1)"' not in text


def test_obsolete_protection_abbreviations_are_rejected_by_simulator():
    simulator = SimN6700Instrument(models={1: "N6775A"})
    assert simulator.execute("CURR:PROT? (@1)") == ""
    assert str(simulator.execute("SYST:ERR?")).startswith("-113")
    assert simulator.execute("OUTP:PROT? (@1)") == ""
    assert str(simulator.execute("SYST:ERR?")).startswith("-113")


def test_clear_errors_on_connect_drains_stale_error_queue_before_strict_writes(tmp_path):
    simulator = SimN6700Instrument(models={1: "N6775A"})
    simulator.execute("CURR:PROT? (@1)")
    assert simulator.errors
    trace = tmp_path / "startup_error_cleanup.jsonl"
    with N6700(
        SimulatedTransport(simulator),
        discover=True,
        clear_errors_on_connect=True,
        audit_log_path=trace,
    ) as inst:
        assert inst.drain_errors() == []
        inst.power_supply(1).output_off()
        inst.check_errors()
    trace_text = trace.read_text(encoding="utf-8")
    assert '"command": "SYST:ERR?"' in trace_text
    assert '"command": "OUTP OFF,(@1)"' in trace_text


def test_n6775a_power_is_calculated_without_unsupported_meas_power_query(tmp_path):
    trace = tmp_path / "n6775a_power_trace.jsonl"
    simulator = SimN6700Instrument(models={1: "N6775A"})
    simulator.channels[1].voltage = 2.0
    simulator.channels[1].current_limit = 0.5
    simulator.channels[1].enabled = True
    with N6700(SimulatedTransport(simulator), audit_log_path=trace) as inst:
        caps = inst.channel(1).capabilities
        assert caps.supports_power_measurement is False
        power = inst.channel(1).measure_power()
        assert power.power_source == "calculated"
        assert power.power_W == pytest.approx(0.4)
        inst.check_errors()

    text = trace.read_text(encoding="utf-8")
    assert '"command": "MEAS:VOLT? (@1)"' in text
    assert '"command": "MEAS:CURR? (@1)"' in text
    assert '"command": "MEAS:POW? (@1)"' not in text


def test_n676_and_n678_support_direct_power_measurement():
    assert classify_module("N6761A").supports_power_measurement is True
    assert classify_module("N6781A").supports_power_measurement is True
    assert classify_module("N6775A").supports_power_measurement is False
    assert classify_module("N6751A").supports_power_measurement is False


def test_empty_quoted_channel_options_are_normalized():
    simulator = SimN6700Instrument(models={1: "N6775A"})
    simulator.channels[1].option = '""'
    with N6700(SimulatedTransport(simulator)) as inst:
        assert inst.channel_options(1) == []
