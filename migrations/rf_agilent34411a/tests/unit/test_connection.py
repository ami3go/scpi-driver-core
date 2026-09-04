"""Connection lifecycle, identity, and multi-alias sessions.

task §14.1 items 1, 12.
"""

from __future__ import annotations

import pytest

from agilent34411a.driver import Agilent34411A
from agilent34411a.exceptions import Agilent34411AConfigurationError, Agilent34411AConnectionError
from rf_agilent34411a.library import Agilent34411ALibrary


def test_simulator_connect_and_identity():
    driver = Agilent34411A.connect_simulated()
    assert driver.connected is True

    identity = driver.identify()
    assert identity.manufacturer == "Agilent Technologies"
    assert identity.model == "34411A"
    assert identity.serial

    assert driver.check_communication() is True
    driver.close()
    assert driver.connected is False


def test_operations_require_connection():
    driver = Agilent34411A.connect_simulated()
    driver.close()
    with pytest.raises(Agilent34411AConnectionError):
        driver.identify()


def test_check_communication_rejects_non_native_scpi_language():
    """task §6 item 7: a unit left in 34401A/34410A emulation mode must fail clearly."""

    driver = Agilent34411A.connect_simulated()
    driver.transport.simulator.language = "34401A"  # type: ignore[attr-defined]
    with pytest.raises(Agilent34411AConfigurationError, match="34401A"):
        driver.check_communication()
    driver.close()


def test_multi_alias_sessions_are_independent():
    lib = Agilent34411ALibrary()
    lib.connect(alias="dmm1", simulated=True)
    lib.connect(alias="dmm2", simulated=True)

    lib.set_range("VOLT", 10.0, alias="dmm1")
    lib.set_range("VOLT", 100.0, alias="dmm2")

    assert lib.get_range("VOLT", alias="dmm1") == 10.0
    assert lib.get_range("VOLT", alias="dmm2") == 100.0
    assert lib.list_multimeter_connections() == ["dmm1", "dmm2"]

    lib.switch_multimeter("dmm1")
    assert lib.get_active_multimeter() == "dmm1"
    assert lib.get_range("VOLT") == 10.0  # uses the active alias when none is given

    lib.disconnect("dmm1")
    assert lib.is_connected("dmm1") is False
    assert lib.is_connected("dmm2") is True
    lib.disconnect("dmm2")


def test_unknown_alias_raises_with_known_aliases_listed():
    lib = Agilent34411ALibrary()
    lib.connect(alias="dmm1", simulated=True)
    with pytest.raises(Agilent34411AConnectionError, match="dmm1"):
        lib.get_range("VOLT", alias="does-not-exist")
    lib.disconnect("dmm1")


def test_is_connected_never_raises_for_missing_session():
    lib = Agilent34411ALibrary()
    assert lib.is_connected("never-connected") is False
    assert lib.is_connected() is False
