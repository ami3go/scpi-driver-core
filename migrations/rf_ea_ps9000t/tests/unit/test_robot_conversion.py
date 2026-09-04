"""Robot-facing data conversion: dataclasses/enums -> plain dicts/scalars.

task §12.1 item 11.
"""

from __future__ import annotations

from ea_ps9000t.enums import RemoteControlOwner
from ea_ps9000t.models import AdjustmentLimits, AlarmCounters, MeasuredValues, ProtectionThresholds
from rf_ea_ps9000t.library import _robot_value


def test_dataclass_converts_to_plain_dict():
    values = MeasuredValues(voltage=12.5, current=3.3, power=41.25)
    result = _robot_value(values)
    assert result == {"voltage": 12.5, "current": 3.3, "power": 41.25}
    assert not hasattr(result, "voltage")  # a real dict, not the dataclass


def test_enum_converts_to_its_value():
    assert _robot_value(RemoteControlOwner.REMOTE) == "REMOTE"


def test_protection_thresholds_dataclass_conversion():
    thresholds = ProtectionThresholds(overvoltage=30.0, overcurrent=20.0, overpower=500.0)
    result = _robot_value(thresholds)
    assert result == {"overvoltage": 30.0, "overcurrent": 20.0, "overpower": 500.0}


def test_adjustment_limits_dataclass_conversion_no_power_low_field():
    limits = AdjustmentLimits(
        voltage_low=0.0, voltage_high=50.0, current_low=0.0, current_high=30.0, power_high=800.0,
    )
    result = _robot_value(limits)
    assert "power_low" not in result
    assert result["power_high"] == 800.0


def test_alarm_counters_dataclass_conversion():
    counters = AlarmCounters(overvoltage=1, overtemperature=2, overpower=3, overcurrent=4, power_fail=5)
    result = _robot_value(counters)
    assert result == {
        "overvoltage": 1,
        "overtemperature": 2,
        "overpower": 3,
        "overcurrent": 4,
        "power_fail": 5,
    }


def test_scalar_passthrough():
    assert _robot_value(42) == 42
    assert _robot_value("text") == "text"
    assert _robot_value(None) is None
    assert _robot_value(True) is True
