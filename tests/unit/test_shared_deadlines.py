"""CORE-ARB-A: monotonic shared deadlines across multi-stage operations."""

from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import TransportTimeoutError
from scpi_driver_core.execution.deadline import Deadline
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.scpi.binary_block import read_definite_length_block
from scpi_driver_core.transport import MockTransport, ReadMode, ReadRequest, TransportState
from scpi_driver_core.transport.visa import VisaTransport
from tests.transport_contract.test_visa_transport_contract import (
    FakeVisaResource,
    install_fake_pyvisa,
)


def test_deadline_uses_one_monotonic_budget() -> None:
    now = [10.0]
    deadline = Deadline(2.0, clock=lambda: now[0])
    assert deadline.remaining() == pytest.approx(2)
    now[0] += 1.9
    assert deadline.remaining() == pytest.approx(0.1)
    now[0] += 0.1
    with pytest.raises(TransportTimeoutError, match="deadline"):
        deadline.remaining()


class SlowMock(MockTransport):
    def __init__(self, now: list[float], *, write_step: float, read_step: float) -> None:
        super().__init__()
        self._now = now
        self._write_step = write_step
        self._read_step = read_step
        self.seen_timeouts: list[float | None] = []

    def write(
        self, data: bytes, *, timeout_s: float | None = None, operation_id: str | None = None
    ):
        result = super().write(data, timeout_s=timeout_s, operation_id=operation_id)
        self._now[0] += self._write_step
        return result

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes:
        self.seen_timeouts.append(timeout_s)
        result = super().read(request, timeout_s=timeout_s, operation_id=operation_id)
        self._now[0] += self._read_step
        return result


def test_direct_binary_reader_shares_header_length_payload_and_terminator_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    transport = SlowMock(now, write_step=0, read_step=0.36)
    transport.open()
    transport.feed(b"#14ABCD\n")
    monkeypatch.setattr(
        "scpi_driver_core.scpi.binary_block.operation_deadline",
        lambda _transport, timeout_s: Deadline(timeout_s, clock=lambda: now[0]),
    )
    with pytest.raises(TransportTimeoutError, match="deadline"):
        read_definite_length_block(transport, timeout_s=1.0, terminator=b"\n")
    assert len(transport.seen_timeouts) == 3
    assert transport.seen_timeouts[0] == pytest.approx(1.0)
    assert transport.seen_timeouts[1] == pytest.approx(0.64)
    assert transport.seen_timeouts[2] == pytest.approx(0.28)
    assert transport.state is TransportState.FAULTED


def test_binary_query_write_and_read_consume_same_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    transport = SlowMock(now, write_step=0.80, read_step=0.12)
    transport.open()
    transport.feed(b"#14ABCD\n")
    monkeypatch.setattr(
        "scpi_driver_core.scpi.client.operation_deadline",
        lambda _transport, timeout_s: Deadline(timeout_s, clock=lambda: now[0]),
    )
    with pytest.raises(TransportTimeoutError):
        ScpiClient(transport).query_binary_block("CURVE?", timeout_s=1)
    assert transport.seen_timeouts == pytest.approx([0.20, 0.08])
    assert transport.state is TransportState.FAULTED
    assert transport.written == b"CURVE?\n"


def test_mock_composite_faults_when_midpoint_exhausts_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [0.0]
    monkeypatch.setattr(
        "scpi_driver_core.transport.mock.Deadline",
        lambda timeout_s: Deadline(timeout_s, clock=lambda: now[0]),
    )
    transport = MockTransport()
    transport.open()
    transport.feed(b"1")
    transport.on_transact_midpoint = lambda: now.__setitem__(0, 2.0)
    with pytest.raises(TransportTimeoutError):
        transport.transact(
            b"MEAS?\n", ReadRequest(mode=ReadMode.EXACT_LENGTH, length=1), timeout_s=1
        )
    assert transport.state is TransportState.FAULTED


def test_visa_partial_writes_cannot_renew_the_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_pyvisa(monkeypatch)
    now = [0.0]
    monkeypatch.setattr(
        "scpi_driver_core.transport.visa.Deadline",
        lambda timeout_s: Deadline(timeout_s, clock=lambda: now[0]),
    )
    transport = VisaTransport("GPIB0::22::INSTR")
    transport.open()
    seen: list[float] = []

    def slow_write(resource: FakeVisaResource, _data: bytes) -> int:
        seen.append(resource.timeout)
        now[0] += 0.4
        return 1

    monkeypatch.setattr(FakeVisaResource, "write_raw", slow_write)
    with pytest.raises(TransportTimeoutError, match="deadline"):
        transport.write(b"long-waveform", timeout_s=1)
    assert len(seen) == 3
    assert seen[0] == pytest.approx(1000)
    assert seen[1] == pytest.approx(600)
    assert seen[2] == pytest.approx(200)
    assert transport.state is TransportState.FAULTED


def test_visa_fragmented_reads_cannot_renew_the_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_fake_pyvisa(monkeypatch)
    now = [0.0]
    monkeypatch.setattr(
        "scpi_driver_core.transport.visa.Deadline",
        lambda timeout_s: Deadline(timeout_s, clock=lambda: now[0]),
    )
    transport = VisaTransport("GPIB0::22::INSTR")
    transport.open()

    def slow_read(_resource: FakeVisaResource, _count: int) -> bytes:
        now[0] += 0.4
        return b"a"

    monkeypatch.setattr(FakeVisaResource, "read_bytes", slow_read)
    with pytest.raises(TransportTimeoutError):
        transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=10), timeout_s=1)
    assert transport.state is TransportState.FAULTED
