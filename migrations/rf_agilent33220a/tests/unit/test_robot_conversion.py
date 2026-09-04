"""Robot-facing data conversion: dataclasses/enums -> plain dicts/scalars.

task §14.1 item 7.
"""

from __future__ import annotations

from agilent33220a.enums import AmplitudeUnit, TriggerSource
from agilent33220a.models import ArbWaveformAttributes, OutputSettings, TriggerSettings
from rf_agilent33220a.library import _robot_value


def test_dataclass_converts_to_plain_dict():
    settings = OutputSettings(
        function="SIN",
        frequency=1000.0,
        amplitude=1.0,
        amplitude_unit="VPP",
        offset=0.0,
        output_enabled=False,
        output_load="50",
        polarity="NORM",
    )
    result = _robot_value(settings)
    assert result == {
        "function": "SIN",
        "frequency": 1000.0,
        "amplitude": 1.0,
        "amplitude_unit": "VPP",
        "offset": 0.0,
        "output_enabled": False,
        "output_load": "50",
        "polarity": "NORM",
    }
    assert not hasattr(result, "function")  # a real dict, not the dataclass


def test_enum_converts_to_its_value():
    assert _robot_value(AmplitudeUnit.VPP) == "VPP"
    assert _robot_value(TriggerSource.BUS) == "BUS"


def test_trigger_settings_dataclass_conversion():
    settings = TriggerSettings(source="EXT", slope="NEG")
    result = _robot_value(settings)
    assert result == {"source": "EXT", "slope": "NEG"}


def test_arb_waveform_attributes_dataclass_conversion():
    attrs = ArbWaveformAttributes(name="MYWAVE", average=0.0, crest_factor=1.4, points=8, peak_to_peak=2.0)
    result = _robot_value(attrs)
    assert result == {
        "name": "MYWAVE",
        "average": 0.0,
        "crest_factor": 1.4,
        "points": 8,
        "peak_to_peak": 2.0,
    }


def test_list_of_dataclasses_converts_recursively():
    values = [
        OutputSettings("SIN", 1.0, 1.0, "VPP", 0.0, False, "50", "NORM"),
        OutputSettings("SQU", 2.0, 1.0, "VPP", 0.0, True, "INF", "INV"),
    ]
    result = _robot_value(values)
    assert isinstance(result, list)
    assert result[0]["function"] == "SIN"
    assert result[1]["output_enabled"] is True


def test_scalar_passthrough():
    assert _robot_value(42) == 42
    assert _robot_value("text") == "text"
    assert _robot_value(None) is None
    assert _robot_value(True) is True
