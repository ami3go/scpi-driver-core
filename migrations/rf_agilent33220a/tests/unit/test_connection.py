"""Connection lifecycle, identity, and multi-alias sessions.

task §14.1 items 1, 7.
"""

from __future__ import annotations

import pytest

from agilent33220a.driver import Agilent33220A
from agilent33220a.exceptions import Agilent33220AConnectionError
from rf_agilent33220a.library import Agilent33220ALibrary


def test_simulator_connect_and_identity():
    driver = Agilent33220A.connect_simulated()
    assert driver.connected is True

    identity = driver.identify()
    assert identity.manufacturer == "Agilent Technologies"
    assert identity.model == "33220A"
    assert identity.serial

    assert driver.check_communication() is True
    driver.close()
    assert driver.connected is False


def test_operations_require_connection():
    driver = Agilent33220A.connect_simulated()
    driver.close()
    with pytest.raises(Agilent33220AConnectionError):
        driver.identify()


def test_multi_alias_sessions_are_independent():
    lib = Agilent33220ALibrary()
    lib.connect(alias="gen1", simulated=True)
    lib.connect(alias="gen2", simulated=True)

    lib.set_frequency(1000.0, alias="gen1")
    lib.set_frequency(5000.0, alias="gen2")

    assert lib.get_frequency("gen1") == 1000.0
    assert lib.get_frequency("gen2") == 5000.0
    assert lib.list_generator_connections() == ["gen1", "gen2"]

    lib.switch_generator("gen1")
    assert lib.get_active_generator() == "gen1"
    assert lib.get_frequency() == 1000.0  # uses the active alias when none is given

    lib.disconnect("gen1")
    assert lib.is_connected("gen1") is False
    assert lib.is_connected("gen2") is True
    lib.disconnect("gen2")


def test_unknown_alias_raises_with_known_aliases_listed():
    lib = Agilent33220ALibrary()
    lib.connect(alias="gen1", simulated=True)
    with pytest.raises(Agilent33220AConnectionError, match="gen1"):
        lib.get_frequency(alias="does-not-exist")
    lib.disconnect("gen1")


def test_is_connected_never_raises_for_missing_session():
    lib = Agilent33220ALibrary()
    assert lib.is_connected("never-connected") is False
    assert lib.is_connected() is False


def test_connect_is_idempotent_for_same_alias():
    lib = Agilent33220ALibrary()
    first = lib.connect(alias="gen1", simulated=True)
    second = lib.connect(alias="gen1", simulated=True)
    assert first["resource"] == second["resource"]
    assert lib.list_generator_connections() == ["gen1"]
    lib.disconnect("gen1")


def test_get_connection_state_reports_disconnected_for_unknown_alias():
    lib = Agilent33220ALibrary()
    state = lib.get_connection_state("nope")
    assert state["connected"] is False
    assert state["state"] == "disconnected"
