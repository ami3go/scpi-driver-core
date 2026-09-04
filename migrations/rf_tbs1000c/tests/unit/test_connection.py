"""Connection lifecycle, identity, and the never-implicit AUTOSet/calibration rule.

task §13.1 items 1, 5, 8.
"""

from __future__ import annotations

import pytest

from rf_tbs1000c.library import Tbs1000cLibrary
from tbs1000c.driver import Tbs1000c
from tbs1000c.exceptions import Tbs1000cConnectionError


def test_simulator_connect_and_identity():
    driver = Tbs1000c.connect_simulated()
    assert driver.connected is True

    identity = driver.identify()
    assert identity.manufacturer == "TEKTRONIX"
    assert identity.model
    assert identity.serial

    assert driver.check_communication() is True
    driver.close()
    assert driver.connected is False


def test_operations_require_connection():
    driver = Tbs1000c.connect_simulated()
    driver.close()
    with pytest.raises(Tbs1000cConnectionError):
        driver.identify()


def test_autoset_and_calibration_never_run_implicitly_from_connect():
    driver = Tbs1000c.connect_simulated()
    simulator = driver.transport.simulator  # type: ignore[attr-defined]
    assert simulator.autoset_calls == 0
    assert simulator.calibration_start_calls == 0

    # A handful of ordinary connection/identity operations must not trigger either.
    driver.identify()
    driver.check_communication()
    driver.get_channel_scale(1)

    assert simulator.autoset_calls == 0
    assert simulator.calibration_start_calls == 0

    # Explicitly calling them is fine and is the only way they run.
    driver.run_autoset()
    assert simulator.autoset_calls == 1
    driver.run_internal_calibration()
    assert simulator.calibration_start_calls == 1


def test_multi_alias_sessions_are_independent():
    lib = Tbs1000cLibrary()
    lib.connect(alias="scope1", simulated=True)
    lib.connect(alias="scope2", simulated=True)

    lib.set_channel_scale(1, 0.2, alias="scope1")
    lib.set_channel_scale(1, 0.8, alias="scope2")

    assert lib.get_channel_scale(1, alias="scope1") == 0.2
    assert lib.get_channel_scale(1, alias="scope2") == 0.8
    assert lib.list_oscilloscope_connections() == ["scope1", "scope2"]

    lib.switch_oscilloscope("scope1")
    assert lib.get_active_oscilloscope() == "scope1"
    assert lib.get_channel_scale(1) == 0.2  # uses the active alias when none is given

    lib.disconnect("scope1")
    assert lib.is_connected("scope1") is False
    assert lib.is_connected("scope2") is True
    lib.disconnect("scope2")


def test_unknown_alias_raises_with_known_aliases_listed():
    lib = Tbs1000cLibrary()
    lib.connect(alias="scope1", simulated=True)
    with pytest.raises(Tbs1000cConnectionError, match="scope1"):
        lib.get_channel_scale(1, alias="does-not-exist")
    lib.disconnect("scope1")
