"""Robot-facing data conversion: dataclasses/enums -> plain dicts/scalars. task §13.1 item 7."""

from __future__ import annotations

from tbs1000c.enums import Coupling, TriggerSlope
from tbs1000c.models import ChannelSettings, TriggerSettings, Waveform, WaveformPreamble
from rf_tbs1000c.library import _robot_value


def test_dataclass_converts_to_plain_dict():
    settings = ChannelSettings(
        channel=1,
        scale=0.5,
        position=0.0,
        offset=0.0,
        coupling="DC",
        bandwidth_limit="FULl",
        probe_gain=1.0,
        label="ICCDATA",
    )
    result = _robot_value(settings)
    assert result == {
        "channel": 1,
        "scale": 0.5,
        "position": 0.0,
        "offset": 0.0,
        "coupling": "DC",
        "bandwidth_limit": "FULl",
        "probe_gain": 1.0,
        "label": "ICCDATA",
    }
    assert not hasattr(result, "channel")  # a real dict, not the dataclass


def test_enum_converts_to_its_value():
    assert _robot_value(Coupling.AC) == "AC"
    assert _robot_value(TriggerSlope.RISE) == "RISE"


def test_nested_dataclass_and_list_convert_recursively():
    preamble = WaveformPreamble(
        bit_nr=8, bn_fmt="RI", byt_nr=1, encdg="BINARY", nr_pt=2, record_length=2,
        wfid="w", x_increment=1.0, x_zero=0.0, x_unit="s",
        y_multiplier=1.0, y_offset=0.0, y_zero=0.0, y_unit="V",
    )
    waveform = Waveform(time_s=[0.0, 1.0], volts=[0.1, 0.2], preamble=preamble)
    result = _robot_value(waveform)
    assert result["time_s"] == [0.0, 1.0]
    assert result["volts"] == [0.1, 0.2]
    assert isinstance(result["preamble"], dict)
    assert result["preamble"]["x_unit"] == "s"


def test_trigger_settings_dataclass_conversion():
    settings = TriggerSettings(source="CH1", slope="RISE", coupling="DC", level=0.5)
    result = _robot_value(settings)
    assert result == {"source": "CH1", "slope": "RISE", "coupling": "DC", "level": 0.5}


def test_scalar_passthrough():
    assert _robot_value(42) == 42
    assert _robot_value("text") == "text"
    assert _robot_value(None) is None
    assert _robot_value(True) is True
