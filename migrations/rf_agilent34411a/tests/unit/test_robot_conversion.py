"""Robot-facing data conversion: dataclasses/enums -> plain dicts/scalars.

task §14.1 item 11.
"""

from __future__ import annotations

from agilent34411a.enums import Function, TriggerSource
from agilent34411a.models import MeasurementSettings, StatisticsResult, TriggerSettings
from rf_agilent34411a.library import _robot_value


def test_dataclass_converts_to_plain_dict():
    settings = MeasurementSettings(
        function="VOLT",
        range_value=10.0,
        auto_range=False,
        nplc=1.0,
        aperture_s=None,
        auto_zero="ON",
        offset_compensation=None,
        ac_filter_bandwidth_hz=None,
        input_impedance_auto=False,
        null_enabled=False,
        null_value=0.0,
    )
    result = _robot_value(settings)
    assert result == {
        "function": "VOLT",
        "range_value": 10.0,
        "auto_range": False,
        "nplc": 1.0,
        "aperture_s": None,
        "auto_zero": "ON",
        "offset_compensation": None,
        "ac_filter_bandwidth_hz": None,
        "input_impedance_auto": False,
        "null_enabled": False,
        "null_value": 0.0,
    }
    assert not hasattr(result, "function")  # a real dict, not the dataclass


def test_enum_converts_to_its_value():
    assert _robot_value(Function.DC_VOLTAGE) == "VOLT"
    assert _robot_value(TriggerSource.BUS) == "BUS"


def test_statistics_result_dataclass_conversion():
    stats = StatisticsResult(average=1.0, minimum=0.5, maximum=1.5, std_deviation=0.1, peak_to_peak=1.0, count=10)
    result = _robot_value(stats)
    assert result == {
        "average": 1.0,
        "minimum": 0.5,
        "maximum": 1.5,
        "std_deviation": 0.1,
        "peak_to_peak": 1.0,
        "count": 10,
    }


def test_trigger_settings_dataclass_conversion():
    settings = TriggerSettings(
        source="EXT", level=0.0, slope="POS", delay_s=0.0, delay_auto=True,
        trigger_count=1.0, sample_count=1.0, sample_source="AUTO", sample_timer_s=1.0,
        pretrigger_sample_count=0.0,
    )
    result = _robot_value(settings)
    assert result["source"] == "EXT"
    assert result["sample_count"] == 1.0


def test_list_of_floats_passthrough():
    assert _robot_value([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]


def test_scalar_passthrough():
    assert _robot_value(42) == 42
    assert _robot_value("text") == "text"
    assert _robot_value(None) is None
    assert _robot_value(True) is True
