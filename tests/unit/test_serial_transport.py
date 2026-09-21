from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

import scpi_driver_core.transport.serial as serial_module
from scpi_driver_core.exceptions import ConfigurationError, TransportError
from scpi_driver_core.transport import FlushDirection, SerialTransport, TransportState
from tests.transport_contract.test_serial_transport_contract import FakeSerial


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSerial.instances.clear()
    FakeSerial.max_write_chunk = None
    backend = SimpleNamespace(Serial=FakeSerial)
    monkeypatch.setattr(serial_module, "_load_serial", lambda: backend)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"port": ""}, "port"),
        ({"port": "x", "baudrate": 0}, "baudrate"),
        ({"port": "x", "timeout_s": 0}, "timeout_s"),
        ({"port": "x", "write_timeout_s": 0}, "write_timeout_s"),
        ({"port": "x", "bytesize": 9}, "bytesize"),
        ({"port": "x", "parity": "X"}, "parity"),
        ({"port": "x", "stopbits": 3}, "stopbits"),
    ],
)
def test_serial_rejects_invalid_configuration(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        SerialTransport(**kwargs)


def test_missing_pyserial_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = importlib.import_module

    def missing(name: str) -> object:
        if name == "serial":
            raise ImportError("missing")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    transport = SerialTransport("COM1")
    with pytest.raises(ConfigurationError, match=r"\[serial\]") as caught:
        transport.open()
    assert caught.value.__cause__ is not None
    assert transport.state is TransportState.CREATED


def test_serial_open_forwards_settings_and_control_lines(fake_backend: None) -> None:
    transport = SerialTransport(
        "COM5",
        baudrate=115200,
        bytesize=7,
        parity="e",
        stopbits=2,
        dtr=False,
        rts=False,
        rtscts=True,
        dsrdtr=True,
        xonxoff=True,
    )
    transport.open()
    resource = FakeSerial.instances[-1]
    assert resource.settings == {
        "port": "COM5",
        "baudrate": 115200,
        "timeout": 5.0,
        "write_timeout": 5.0,
        "bytesize": 7,
        "parity": "E",
        "stopbits": 2,
        "rtscts": True,
        "dsrdtr": True,
        "xonxoff": True,
    }
    assert resource.dtr is False
    assert resource.rts is False


def test_serial_flush_maps_directions(fake_backend: None) -> None:
    transport = SerialTransport("COM1")
    transport.open()
    resource = FakeSerial.instances[-1]
    transport.flush(FlushDirection.INPUT)
    transport.flush(FlushDirection.OUTPUT)
    transport.flush(FlushDirection.BOTH)
    assert resource.input_flushes == 2
    assert resource.output_flushes == 2


def test_serial_open_failure_is_chained(
    fake_backend: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenSerial:
        def __init__(self, **settings: object) -> None:
            del settings
            raise OSError("busy")

    backend = SimpleNamespace(Serial=BrokenSerial)
    monkeypatch.setattr(serial_module, "_load_serial", lambda: backend)
    transport = SerialTransport("COM1")
    with pytest.raises(TransportError, match="open") as caught:
        transport.open()
    assert caught.value.__cause__ is not None
    assert transport.state is TransportState.FAULTED


def test_serial_descriptor_includes_flow_control(fake_backend: None) -> None:
    descriptor = SerialTransport(
        "COM5", baudrate=19200, parity="o", rtscts=True, dsrdtr=True, xonxoff=False
    ).descriptor
    assert descriptor.kind == "serial"
    assert descriptor.address == "COM5"
    assert descriptor.metadata == {
        "baudrate": "19200",
        "parity": "O",
        "rtscts": "True",
        "dsrdtr": "True",
        "xonxoff": "False",
    }
