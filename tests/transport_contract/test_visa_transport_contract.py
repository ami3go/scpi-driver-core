from __future__ import annotations

from collections import deque
from types import SimpleNamespace
from typing import Any, ClassVar

import pytest

import scpi_driver_core.transport.visa as visa_module
from scpi_driver_core.transport import Transport, VisaTransport
from tests.transport_contract.contract import TransportContract

VI_ERROR_TMO = -1073807339


class FakeVisaIOError(Exception):
    """Stands in for pyvisa.errors.VisaIOError, matched by its error_code."""

    def __init__(self, message: str, error_code: int = VI_ERROR_TMO) -> None:
        super().__init__(message)
        self.error_code = error_code


class FakeVisaResource:
    """A message-oriented VISA session.

    Fed data keeps its message boundaries for ``read_raw``, while ``read_bytes``
    pulls across them, which is how a real VISA session behaves.
    """

    instances: ClassVar[list[FakeVisaResource]] = []
    max_write_chunk: ClassVar[int | None] = None

    def __init__(self, resource_name: str, **settings: Any) -> None:
        self.resource_name = resource_name
        self.settings = settings
        self.timeout = 0.0
        self.chunk_size = 0
        self.messages: deque[bytes] = deque()
        self.written = bytearray()
        self.fail_read: Exception | None = None
        self.clears = 0
        self.closed = False
        type(self).instances.append(self)

    def feed(self, data: bytes) -> None:
        self.messages.append(data)

    def write_raw(self, data: bytes) -> int:
        count = min(len(data), self.max_write_chunk or max(len(data), 1))
        self.written.extend(data[:count])
        return count

    def _check_read(self) -> None:
        if self.fail_read is not None:
            error, self.fail_read = self.fail_read, None
            raise error

    def read_raw(self, size: int | None = None) -> bytes:
        del size
        self._check_read()
        if not self.messages:
            raise FakeVisaIOError("VI_ERROR_TMO")
        return self.messages.popleft()

    def read_bytes(self, count: int) -> bytes:
        self._check_read()
        taken = bytearray()
        while len(taken) < count:
            if not self.messages:
                raise FakeVisaIOError("VI_ERROR_TMO")
            message = self.messages.popleft()
            needed = count - len(taken)
            if len(message) > needed:
                taken += message[:needed]
                self.messages.appendleft(message[needed:])
                break
            taken += message
        return bytes(taken)

    def clear(self) -> None:
        self.clears += 1
        self.messages.clear()

    def close(self) -> None:
        self.closed = True


class FakeResourceManager:
    instances: ClassVar[list[FakeResourceManager]] = []

    def __init__(self, visa_library: str = "") -> None:
        self.visa_library = visa_library
        self.closed = False
        self.opened: list[str] = []
        type(self).instances.append(self)

    def open_resource(self, resource_name: str, **settings: Any) -> FakeVisaResource:
        self.opened.append(resource_name)
        return FakeVisaResource(resource_name, **settings)

    def close(self) -> None:
        self.closed = True


def install_fake_pyvisa(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeVisaResource.instances.clear()
    FakeResourceManager.instances.clear()
    FakeVisaResource.max_write_chunk = None
    fake = SimpleNamespace(ResourceManager=FakeResourceManager)
    monkeypatch.setattr(visa_module, "_load_pyvisa", lambda: fake)


class TestVisaTransportContract(TransportContract):
    supports_failure_injection = True
    supports_partial_write = True

    @pytest.fixture(autouse=True)
    def fake_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        install_fake_pyvisa(monkeypatch)

    def create_transport(self) -> Transport:
        return VisaTransport("GPIB0::22::INSTR", timeout_s=0.1)

    def prime(self, transport: Transport, data: bytes) -> None:
        assert isinstance(transport, VisaTransport)
        resource = transport._resource
        assert isinstance(resource, FakeVisaResource)
        resource.feed(data)

    def inject_read_failure(self, transport: Transport, error: Exception) -> None:
        assert isinstance(transport, VisaTransport)
        resource = transport._resource
        assert isinstance(resource, FakeVisaResource)
        resource.fail_read = error

    def create_fragmenting_transport(self, chunk_size: int) -> Transport:
        FakeVisaResource.max_write_chunk = chunk_size
        return self.create_transport()
