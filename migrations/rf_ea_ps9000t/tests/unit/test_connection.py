"""Connection lifecycle, identity, and the mandatory remote-control acquisition.

task §12.1 items 1, 2, 3, 12.
"""

from __future__ import annotations

import pytest

from ea_ps9000t.driver import EaPs9000T
from ea_ps9000t.enums import RemoteControlOwner
from ea_ps9000t.exceptions import EaPs9000TConnectionError, EaPs9000TValidationError
from ea_ps9000t.simulator import SimEaPs9000TInstrument
from rf_ea_ps9000t.library import EaPs9000TLibrary, _resolve_visa_resource


def test_simulator_connect_acquires_remote_control_and_identity():
    driver = EaPs9000T.connect_simulated()
    assert driver.connected is True
    assert driver.get_remote_control_owner() == RemoteControlOwner.REMOTE

    identity = driver.identify()
    assert identity.manufacturer == "EA-Elektro-Automatik"
    assert identity.model
    assert identity.serial
    assert identity.user_text == ""  # empty when never set (task §12.1 item 1)

    assert driver.check_communication() is True
    driver.close()
    assert driver.connected is False


def test_identity_five_field_parse_with_user_text():
    driver = EaPs9000T.connect_simulated()
    driver.set_user_text("bench 3")
    identity = driver.identify(refresh=True)
    assert identity.user_text == "bench 3"
    assert identity.raw.count(",") == 4  # 5 fields
    driver.close()


def test_connect_raises_typed_error_when_remote_control_is_refused():
    """task §12.1 item 2: the core safety-relevant behavior test for this driver."""

    simulator = SimEaPs9000TInstrument()
    simulator.force_lock_refusal = True
    with pytest.raises(EaPs9000TConnectionError, match="refused"):
        EaPs9000T.connect_simulated(simulator)
    # The refused-lock owner must be named in the error, not just "refused".
    assert simulator.lock_owner == "NONE"


def test_acquire_remote_control_tolerates_a_brief_owner_readback_race():
    """Reproduces a real-hardware finding (RFDS-019 conformance run): the front panel
    already showed "Remote: USB" while an immediate SYSTem:LOCK:OWNer? still read back
    NONE. acquire_remote_control must re-check briefly rather than treating the first
    stale read as a genuine refusal."""

    class DelayedOwnerTransport:
        resource = "FAKE::INSTR"
        timeout_s = 5.0

        def __init__(self):
            self._open = True
            self._owner_queries = 0

        def is_open(self):
            return self._open

        def write(self, _command):
            pass

        def query(self, command):
            if command == "*OPC?":
                return "1"
            if command == "SYSTem:LOCK:OWNer?":
                self._owner_queries += 1
                return "NONE" if self._owner_queries == 1 else "REMOTE"
            raise AssertionError(f"unexpected query: {command}")

        def close(self):
            self._open = False

    transport = DelayedOwnerTransport()
    driver = EaPs9000T(transport)
    driver.acquire_remote_control()
    assert transport._owner_queries == 2
    driver.close()


def test_disconnect_releases_remote_control_before_closing():
    """task §12.1 item 3."""

    simulator = SimEaPs9000TInstrument()
    driver = EaPs9000T.connect_simulated(simulator)
    assert simulator.lock_owner == "REMOTE"
    driver.close()
    assert simulator.lock_owner == "NONE"


def test_operations_require_connection():
    driver = EaPs9000T.connect_simulated()
    driver.close()
    with pytest.raises(EaPs9000TConnectionError):
        driver.identify()


def test_multi_alias_sessions_are_independent():
    lib = EaPs9000TLibrary()
    lib.connect(alias="psu1", simulated=True)
    lib.connect(alias="psu2", simulated=True)

    lib.set_voltage(12.0, alias="psu1")
    lib.set_voltage(24.0, alias="psu2")

    assert lib.get_voltage("psu1") == 12.0
    assert lib.get_voltage("psu2") == 24.0
    assert lib.list_power_supply_connections() == ["psu1", "psu2"]

    lib.switch_power_supply("psu1")
    assert lib.get_active_power_supply() == "psu1"
    assert lib.get_voltage() == 12.0  # uses the active alias when none is given

    lib.disconnect("psu1")
    assert lib.is_connected("psu1") is False
    assert lib.is_connected("psu2") is True
    lib.disconnect("psu2")


def test_unknown_alias_raises_with_known_aliases_listed():
    lib = EaPs9000TLibrary()
    lib.connect(alias="psu1", simulated=True)
    with pytest.raises(EaPs9000TConnectionError, match="psu1"):
        lib.get_voltage(alias="does-not-exist")
    lib.disconnect("psu1")


def test_is_connected_never_raises_for_missing_session():
    lib = EaPs9000TLibrary()
    assert lib.is_connected("never-connected") is False
    assert lib.is_connected() is False


@pytest.mark.parametrize(
    "com_port",
    [5, "5", "COM5", "com5"],
)
def test_resolve_visa_resource_expands_com_port_argument(com_port):
    assert _resolve_visa_resource(None, com_port) == "ASRL5::INSTR"


@pytest.mark.parametrize(
    "resource",
    ["5", "COM5", "com5"],
)
def test_resolve_visa_resource_expands_bare_resource_shorthand(resource):
    assert _resolve_visa_resource(resource, None) == "ASRL5::INSTR"


def test_resolve_visa_resource_passes_full_visa_strings_through_unchanged():
    assert _resolve_visa_resource("ASRL5::INSTR", None) == "ASRL5::INSTR"
    assert _resolve_visa_resource("TCPIP0::192.168.0.2::5025::SOCKET", None) == (
        "TCPIP0::192.168.0.2::5025::SOCKET"
    )


def test_resolve_visa_resource_com_port_takes_precedence_over_resource():
    assert _resolve_visa_resource("TCPIP0::192.168.0.2::5025::SOCKET", 7) == "ASRL7::INSTR"


def test_resolve_visa_resource_rejects_invalid_com_port():
    with pytest.raises(EaPs9000TValidationError, match="com_port"):
        _resolve_visa_resource(None, "not-a-port")


def test_resolve_visa_resource_requires_resource_or_com_port():
    with pytest.raises(EaPs9000TValidationError, match="resource or com_port"):
        _resolve_visa_resource(None, None)


def test_connect_com_port_idempotent_for_the_same_alias(monkeypatch):
    """A repeated ``com_port=5`` connect must recognize it as the same
    resource as the first call, even though the first call normalized the
    shorthand to ``ASRL5::INSTR`` before storing it (task §7)."""

    simulator = SimEaPs9000TInstrument()

    def fake_connect_visa(resource, timeout_s=5.0):
        assert resource == "ASRL5::INSTR"
        driver = EaPs9000T.connect_simulated(simulator)
        driver.transport.resource = resource  # mimic PyvisaTransport, which reports the real resource
        return driver

    monkeypatch.setattr(EaPs9000T, "connect_visa", staticmethod(fake_connect_visa))

    lib = EaPs9000TLibrary()
    first = lib.connect(alias="bench", com_port=5)
    second = lib.connect(alias="bench", com_port=5)
    assert first["resource"] == second["resource"] == "ASRL5::INSTR"

    # A bare re-connect with no resource/com_port on an already-connected
    # alias must stay a no-op rather than demanding one be supplied again.
    third = lib.connect(alias="bench")
    assert third["resource"] == "ASRL5::INSTR"

    lib.disconnect("bench")
