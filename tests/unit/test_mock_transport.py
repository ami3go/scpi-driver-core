from __future__ import annotations

import contextlib
import threading

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    NotConnectedError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.transport import (
    FlushDirection,
    MockTransport,
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    Transport,
    TransportDescriptor,
    TransportState,
)


def opened(**kwargs: object) -> MockTransport:
    transport = MockTransport(**kwargs)  # type: ignore[arg-type]
    transport.open()
    return transport


def test_mock_transport_satisfies_the_protocol() -> None:
    assert isinstance(MockTransport(), Transport)


# -- configuration --------------------------------------------------------


@pytest.mark.parametrize("timeout_s", [0.0, -1.0, float("inf"), float("nan")])
def test_rejects_unbounded_default_timeout(timeout_s: float) -> None:
    with pytest.raises(ConfigurationError):
        MockTransport(timeout_s=timeout_s)


@pytest.mark.parametrize("chunk", [0, -3])
def test_rejects_nonpositive_write_chunk(chunk: int) -> None:
    with pytest.raises(ConfigurationError):
        MockTransport(max_write_chunk=chunk)


@pytest.mark.parametrize("timeout_s", [0.0, -1.0, float("inf")])
def test_rejects_unbounded_per_call_timeout(timeout_s: float) -> None:
    transport = opened()
    with pytest.raises(ConfigurationError):
        transport.write(b"x", timeout_s=timeout_s)
    with pytest.raises(ConfigurationError):
        transport.read(ReadRequest(mode=ReadMode.AVAILABLE), timeout_s=timeout_s)


def test_default_descriptor_and_override() -> None:
    assert MockTransport().descriptor.kind == "mock"
    custom = TransportDescriptor(kind="mock", address="sim://psu")
    assert MockTransport(descriptor=custom).descriptor is custom


# -- state machine --------------------------------------------------------


def test_open_records_transient_opening_state() -> None:
    transport = MockTransport()
    transport.open()
    assert transport.transitions == [TransportState.OPENING, TransportState.OPEN]


def test_close_records_transient_closing_state() -> None:
    transport = opened()
    transport.transitions.clear()
    transport.close()
    assert transport.transitions == [TransportState.CLOSING, TransportState.CLOSED]


def test_open_is_idempotent_and_does_not_reacquire() -> None:
    transport = opened()
    transport.open()
    assert transport.open_count == 1


def test_close_releases_the_resource_once() -> None:
    transport = opened()
    transport.close()
    transport.close()
    assert transport.release_count == 1


def test_reopen_from_faulted_releases_the_failed_resource_first() -> None:
    transport = opened()
    transport.fail_next_read(TransportError("dead"))
    with pytest.raises(TransportError):
        transport.read(ReadRequest(mode=ReadMode.AVAILABLE))

    assert transport.state is TransportState.FAULTED
    assert transport.release_count == 1

    transport.open()
    assert transport.open_count == 2
    assert transport.release_count == 1  # released at fault time, not re-released


def test_failed_open_faults_the_transport() -> None:
    transport = MockTransport()
    transport.fail_next_open(TransportError("refused"))
    with pytest.raises(TransportError):
        transport.open()
    assert transport.state is TransportState.FAULTED
    assert transport.open_count == 0


def test_open_after_failed_open_succeeds() -> None:
    transport = MockTransport()
    transport.fail_next_open(TransportError("refused"))
    with pytest.raises(TransportError):
        transport.open()
    transport.open()
    assert transport.is_open is True


def test_non_faulting_failure_leaves_transport_open() -> None:
    transport = opened()
    transport.fail_next_write(TransportTimeoutError("slow"), fault=False)
    with pytest.raises(TransportTimeoutError):
        transport.write(b"*RST\n")
    assert transport.state is TransportState.OPEN


def test_injection_fires_only_once() -> None:
    transport = opened()
    transport.fail_next_write(TransportTimeoutError("slow"), fault=False)
    with pytest.raises(TransportTimeoutError):
        transport.write(b"a")
    assert transport.write(b"b").bytes_written == 1


def test_simulate_disconnect_faults_and_discards_buffer() -> None:
    transport = opened()
    transport.feed(b"stale\n")
    transport.simulate_disconnect()
    assert transport.state is TransportState.FAULTED
    assert transport.pending_bytes == 0
    with pytest.raises(NotConnectedError):
        transport.write(b"*IDN?\n")


# -- reads ----------------------------------------------------------------


def test_backend_defined_message_pops_one_fed_chunk() -> None:
    transport = opened()
    transport.feed(b"first")
    transport.feed(b"second")
    request = ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)
    assert transport.read(request) == b"first"
    assert transport.read(request) == b"second"


def test_stream_modes_see_chunks_concatenated() -> None:
    transport = opened()
    transport.feed(b"KEYSIGHT,")
    transport.feed(b"N6700C\n")
    data = transport.read(ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"))
    assert data == b"KEYSIGHT,N6700C"


def test_partial_chunk_consumption_leaves_the_remainder() -> None:
    transport = opened()
    transport.feed(b"0123456789")
    assert transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=3)) == b"012"
    assert transport.read(ReadRequest(mode=ReadMode.AVAILABLE)) == b"3456789"


def test_available_returns_empty_when_nothing_buffered() -> None:
    transport = opened()
    assert transport.read(ReadRequest(mode=ReadMode.AVAILABLE)) == b""


def test_available_is_capped_by_maximum_size() -> None:
    transport = opened()
    transport.feed(b"x" * 100)
    data = transport.read(ReadRequest(mode=ReadMode.AVAILABLE, maximum_size=10))
    assert data == b"x" * 10
    assert transport.pending_bytes == 90


def test_backend_defined_message_rejects_oversized_message() -> None:
    transport = opened()
    transport.feed(b"x" * 100)
    with pytest.raises(TransportError):
        transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE, maximum_size=10))


def test_backend_defined_message_times_out_when_empty() -> None:
    transport = opened()
    with pytest.raises(TransportTimeoutError):
        transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE))


def test_exact_length_times_out_when_short() -> None:
    transport = opened()
    transport.feed(b"ab")
    with pytest.raises(TransportTimeoutError):
        transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=4))


def test_up_to_length_times_out_when_empty() -> None:
    transport = opened()
    with pytest.raises(TransportTimeoutError):
        transport.read(ReadRequest(mode=ReadMode.UP_TO_LENGTH, length=4))


def test_up_to_length_truncates_to_length() -> None:
    transport = opened()
    transport.feed(b"0123456789")
    assert transport.read(ReadRequest(mode=ReadMode.UP_TO_LENGTH, length=4)) == b"0123"


def test_terminator_beyond_maximum_size_is_an_error_not_a_timeout() -> None:
    transport = opened()
    transport.feed(b"x" * 20 + b"\n")
    with pytest.raises(TransportError) as excinfo:
        transport.read(
            ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n", maximum_size=8)
        )
    assert not isinstance(excinfo.value, TransportTimeoutError)


def test_multibyte_terminator_is_stripped_whole() -> None:
    transport = opened()
    transport.feed(b"DATA\r\n")
    data = transport.read(ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\r\n"))
    assert data == b"DATA"


def test_embedded_terminator_bytes_are_not_trimmed() -> None:
    """A payload byte that happens to equal the terminator must survive."""
    transport = opened()
    transport.feed(b"\x00\n\x00\n")
    data = transport.read(
        ReadRequest(mode=ReadMode.EXACT_LENGTH, length=4),
    )
    assert data == b"\x00\n\x00\n"


# -- writes ---------------------------------------------------------------


def test_written_accumulates_exact_bytes() -> None:
    transport = opened()
    transport.write(b"VOLT 1\n")
    transport.write(b"VOLT 2\n")
    assert transport.written == b"VOLT 1\nVOLT 2\n"


def test_write_is_fragmented_but_complete() -> None:
    transport = opened(max_write_chunk=3)
    assert transport.write(b"0123456789").bytes_written == 10
    assert transport.write_chunks == [b"012", b"345", b"678", b"9"]
    assert transport.written == b"0123456789"


def test_unfragmented_write_is_a_single_chunk() -> None:
    transport = opened()
    transport.write(b"0123456789")
    assert transport.write_chunks == [b"0123456789"]


def test_empty_write_produces_no_chunks() -> None:
    transport = opened()
    transport.write(b"")
    assert transport.write_chunks == []


# -- flush ----------------------------------------------------------------


@pytest.mark.parametrize("direction", [FlushDirection.INPUT, FlushDirection.BOTH])
def test_flush_discards_input(direction: FlushDirection) -> None:
    transport = opened()
    transport.feed(b"stale\n")
    transport.flush(direction)
    assert transport.pending_bytes == 0


def test_flush_output_leaves_input_alone() -> None:
    transport = opened()
    transport.feed(b"keep\n")
    transport.flush(FlushDirection.OUTPUT)
    assert transport.pending_bytes == len(b"keep\n")


# -- operation log --------------------------------------------------------


def test_operations_record_kind_data_and_correlation() -> None:
    transport = opened()
    transport.feed(b"ok\n")
    transport.write(b"*IDN?\n", operation_id="op-1")
    transport.read(ReadRequest(mode=ReadMode.AVAILABLE), operation_id="op-1")
    transport.close()

    kinds = [op.kind for op in transport.operations]
    assert kinds == ["open", "write", "read", "close"]
    assert transport.operations[1].data == b"*IDN?\n"
    assert transport.operations[1].operation_id == "op-1"
    assert transport.operations[2].data == b"ok\n"


def test_operation_records_effective_timeout() -> None:
    transport = opened(timeout_s=2.5)
    transport.write(b"a")
    transport.write(b"b", timeout_s=0.75)
    assert transport.operations[1].timeout_s == 2.5
    assert transport.operations[2].timeout_s == 0.75


def test_default_timeout_is_exposed() -> None:
    assert MockTransport(timeout_s=1.5).default_timeout_s == 1.5


# -- transactions ---------------------------------------------------------


def test_transact_records_replay_policy() -> None:
    transport = opened()
    transport.feed(b"a\n")
    transport.feed(b"b\n")
    request = ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")
    transport.transact(b"Q1\n", request)
    transport.transact(b"Q2\n", request, replay_policy=ReplayPolicy.SAFE)
    assert transport.replay_policies == [ReplayPolicy.NEVER, ReplayPolicy.SAFE]


def test_transact_does_not_retry_on_failure() -> None:
    transport = opened()
    transport.fail_next_read(TransportError("dead"))
    with pytest.raises(TransportError):
        transport.transact(
            b"Q\n",
            ReadRequest(mode=ReadMode.AVAILABLE),
            replay_policy=ReplayPolicy.SAFE,
        )
    assert transport.written == b"Q\n"  # sent exactly once


def test_transact_holds_the_lock_across_write_and_read() -> None:
    """With a forced yield between the halves, the log must still pair W/R."""
    transport = opened()
    count = 8
    for index in range(count):
        transport.feed(f"r{index}\n".encode())

    barrier = threading.Barrier(count)

    def midpoint() -> None:
        # If transact did not hold its lock, every thread would pile up here
        # between its own write and read, interleaving the operation log.
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(timeout=0.2)

    transport.on_transact_midpoint = midpoint
    request = ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")

    threads = [
        threading.Thread(target=lambda: transport.transact(b"Q\n", request)) for _ in range(count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    io_kinds = [op.kind for op in transport.operations if op.kind in ("write", "read")]
    assert io_kinds == ["write", "read"] * count
