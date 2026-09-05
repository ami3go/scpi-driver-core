from dataclasses import dataclass

import pytest

from rf_eresistor.library import EResistorLibrary, _bool, _robot_value


@dataclass
class Result:
    channel: int
    mask: str


def test_robot_value_converts_dataclass_and_integer_keys():
    assert _robot_value({1: Result(1, "0001")}) == {"1": {"channel": 1, "mask": "0001"}}


@pytest.mark.parametrize("value", [True, "TRUE", "yes", "1", 1])
def test_boolean_true(value):
    assert _bool(value) is True


@pytest.mark.parametrize("value", [False, "FALSE", "no", "0", 0])
def test_boolean_false(value):
    assert _bool(value) is False


def test_invalid_boolean_rejected():
    with pytest.raises(ValueError):
        _bool("perhaps")


def test_operation_requires_connection():
    lib = EResistorLibrary()
    with pytest.raises(RuntimeError, match="not connected"):
        lib.get_identity()


class FakeClient:
    def __init__(self, host="192.168.0.55"):
        from eresistor_driver.models import ConnectionState, ShutdownPolicy

        self.closed = False
        self.shutdown_policy = ShutdownPolicy.ALL_OFF
        self.host = host
        self.connection_state = ConnectionState.CONNECTED

    def idn(self):
        return "OpenBench,E-Resistor,SN001,0.4.0"

    def ping(self):
        return True

    def close(self):
        self.closed = True


def test_disconnect_is_idempotent():
    lib = EResistorLibrary()
    fake = FakeClient()
    lib._client = fake
    lib.disconnect()
    assert fake.closed
    assert lib._client is None
    lib.disconnect()


def test_generic_keywords_reflect_connected_state():
    lib = EResistorLibrary()
    assert lib.is_connected() is False
    state = lib.get_connection_state()
    assert state["connected"] is False
    assert state["state"] == "disconnected"

    lib._client = FakeClient()
    assert lib.is_connected() is True
    assert lib.check_communication() is True
    assert lib.get_identity_generic() == "OpenBench,E-Resistor,SN001,0.4.0"

    state = lib.get_connection_state(refresh=True)
    assert state["connected"] is True
    assert state["state"] == "connected"
    assert state["resource"] == "192.168.0.55"
    assert state["identity"] == "OpenBench,E-Resistor,SN001,0.4.0"


def test_generic_connect_is_idempotent_for_same_resource():
    lib = EResistorLibrary()
    fake = FakeClient()
    lib._client = fake
    result = lib.generic_connect(resource="192.168.0.55")
    assert result["connected"] is True
    assert result["resource"] == "192.168.0.55"


def test_generic_connect_rejects_conflicting_resource():
    lib = EResistorLibrary()
    lib._client = FakeClient()
    with pytest.raises(RuntimeError, match="Already connected"):
        lib.generic_connect(resource="192.168.0.99")


def test_generic_disconnect_is_idempotent():
    lib = EResistorLibrary()
    fake = FakeClient()
    lib._client = fake
    lib.generic_disconnect()
    assert fake.closed
    assert lib._client is None
    lib.generic_disconnect()

