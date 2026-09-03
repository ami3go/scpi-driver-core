from __future__ import annotations

from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

import scpi_driver_core.transport.serial as serial_module
from scpi_driver_core.transport import SerialTransport, Transport
from tests.transport_contract.contract import TransportContract


class FakeSerial:
    instances: ClassVar[list[FakeSerial]] = []
    max_write_chunk: ClassVar[int | None] = None

    def __init__(self, **settings: Any) -> None:
        self.settings = settings
        self.timeout = settings["timeout"]
        self.write_timeout = settings["write_timeout"]
        self.dtr = True
        self.rts = True
        self.inbound = bytearray()
        self.written = bytearray()
        self.fail_read: Exception | None = None
        self.input_flushes = 0
        self.output_flushes = 0
        type(self).instances.append(self)

    @property
    def in_waiting(self) -> int:
        return len(self.inbound)

    def write(self, data: bytes) -> int:
        count = min(len(data), self.max_write_chunk or max(len(data), 1))
        self.written.extend(data[:count])
        return count

    def read(self, size: int) -> bytes:
        if self.fail_read is not None:
            error, self.fail_read = self.fail_read, None
            raise error
        count = min(size, len(self.inbound))
        data = bytes(self.inbound[:count])
        del self.inbound[:count]
        return data

    def read_until(self, expected: bytes, size: int) -> bytes:
        end = self.inbound.find(expected)
        count = min(size, len(self.inbound) if end < 0 else end + len(expected))
        return self.read(count)

    def reset_input_buffer(self) -> None:
        self.input_flushes += 1
        self.inbound.clear()

    def reset_output_buffer(self) -> None:
        self.output_flushes += 1

    def close(self) -> None:
        pass


class TestSerialTransportContract(TransportContract):
    supports_failure_injection = True
    supports_partial_write = True

    @pytest.fixture(autouse=True)
    def fake_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        FakeSerial.instances.clear()
        FakeSerial.max_write_chunk = None
        backend = SimpleNamespace(Serial=FakeSerial)
        monkeypatch.setattr(serial_module, "_load_serial", lambda: backend)

    def create_transport(self) -> Transport:
        return SerialTransport("loop://", timeout_s=0.1, write_timeout_s=0.1)

    def prime(self, transport: Transport, data: bytes) -> None:
        assert isinstance(transport, SerialTransport)
        resource = transport._resource
        assert isinstance(resource, FakeSerial)
        resource.inbound.extend(data)

    def inject_read_failure(self, transport: Transport, error: Exception) -> None:
        assert isinstance(transport, SerialTransport)
        resource = transport._resource
        assert isinstance(resource, FakeSerial)
        resource.fail_read = error

    def create_fragmenting_transport(self, chunk_size: int) -> Transport:
        FakeSerial.max_write_chunk = chunk_size
        return self.create_transport()
