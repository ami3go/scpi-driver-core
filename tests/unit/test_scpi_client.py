from __future__ import annotations

import contextlib
import math
import threading
from collections.abc import Callable

import pytest

from scpi_driver_core import (
    ConfigurationError,
    ProtocolError,
    ResponseParseError,
    ScpiClient,
)
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.scpi.binary_block import decode_definite_length_block
from scpi_driver_core.transport import (
    MockTransport,
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    Transport,
)


def opened(**kwargs: object) -> MockTransport:
    transport = MockTransport(**kwargs)
    transport.open()
    return transport


def query_request() -> ReadRequest:
    return ReadRequest(
        mode=ReadMode.UNTIL_TERMINATOR,
        terminator=b"\n",
        include_terminator=True,
    )


def test_client_satisfies_transport_agnostic_construction() -> None:
    transport: Transport = opened()
    client = ScpiClient(transport)
    assert client.transport is transport
    assert client.is_open


def test_default_properties() -> None:
    transport = MockTransport()
    client = ScpiClient(transport)
    assert client.codec == ScpiTextCodec()
    assert client.timeout_s is None
    assert client.response_request == query_request()
    assert not client.is_open


def test_no_response_terminator_uses_backend_message() -> None:
    client = ScpiClient(MockTransport(), codec=ScpiTextCodec(response_terminator=None))
    assert client.response_request.mode is ReadMode.BACKEND_DEFINED_MESSAGE
    assert client.response_request.maximum_size == client.codec.maximum_response_size


def test_custom_response_request_is_preserved() -> None:
    request = ReadRequest(mode=ReadMode.EXACT_LENGTH, length=4)
    client = ScpiClient(MockTransport(), response_request=request)
    assert client.response_request is request


@pytest.mark.parametrize("timeout", [0.0, -1.0, math.inf, -math.inf, math.nan])
def test_constructor_rejects_invalid_timeout(timeout: float) -> None:
    with pytest.raises(ConfigurationError, match="finite and positive"):
        ScpiClient(MockTransport(), timeout_s=timeout)


@pytest.mark.parametrize("timeout", [0.0, -1.0, math.inf, -math.inf, math.nan])
def test_operation_rejects_invalid_timeout(timeout: float) -> None:
    client = ScpiClient(opened())
    with pytest.raises(ConfigurationError, match="finite and positive"):
        client.write("*CLS", timeout_s=timeout)


def test_write_frames_text_and_returns_none() -> None:
    transport = opened()
    client = ScpiClient(transport)
    assert client.write("*CLS") is None
    assert transport.written == b"*CLS\n"


def test_write_bytes_bypasses_codec() -> None:
    transport = opened()
    client = ScpiClient(transport)
    client.write_bytes(b"\xff\x00")
    assert transport.written == b"\xff\x00"


def test_read_bytes_bypasses_codec() -> None:
    transport = opened()
    transport.feed(b"\xff\x00")
    client = ScpiClient(transport)
    assert client.read_bytes(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=2)) == b"\xff\x00"


def test_transact_bytes_bypasses_codec_and_forwards_replay_policy() -> None:
    transport = opened()
    transport.feed(b"reply")
    client = ScpiClient(transport)
    response = ReadRequest(mode=ReadMode.EXACT_LENGTH, length=5)
    assert client.transact_bytes(b"raw", response, replay_policy=ReplayPolicy.SAFE) == b"reply"
    assert transport.written == b"raw"
    assert transport.replay_policies == [ReplayPolicy.SAFE]


def test_query_frames_and_decodes() -> None:
    transport = opened()
    transport.feed(b"ACME,MODEL\n")
    client = ScpiClient(transport)
    assert client.query("*IDN?") == "ACME,MODEL"
    assert transport.written == b"*IDN?\n"


def test_query_defaults_to_no_replay() -> None:
    transport = opened()
    transport.feed(b"1\n")
    ScpiClient(transport).query("READ?")
    assert transport.replay_policies == [ReplayPolicy.NEVER]


def test_query_forwards_safe_replay() -> None:
    transport = opened()
    transport.feed(b"1\n")
    ScpiClient(transport).query("READ?", replay_policy=ReplayPolicy.SAFE)
    assert transport.replay_policies == [ReplayPolicy.SAFE]


@pytest.mark.parametrize(
    ("method", "response", "expected"),
    [
        ("query_float", b"1.25\n", 1.25),
        ("query_int", b"2.000E+00\n", 2),
        ("query_bool", b"ON\n", True),
        ("query_csv", b'a,"b,c"\n', ["a", "b,c"]),
        ("query_optional_unit_float", b"3.5 V\n", 3.5),
    ],
)
def test_typed_queries(method: str, response: bytes, expected: object) -> None:
    transport = opened()
    transport.feed(response)
    client = ScpiClient(transport)
    result = getattr(client, method)("MEAS?")
    assert result == expected


def test_query_float_forwards_allow_non_finite() -> None:
    transport = opened()
    transport.feed(b"INF\n")
    assert ScpiClient(transport).query_float("MEAS?", allow_non_finite=True) == math.inf


def test_query_optional_unit_float_forwards_options() -> None:
    transport = opened()
    transport.feed(b"INF V\n")
    result = ScpiClient(transport).query_optional_unit_float(
        "MEAS?", expected_unit="v", allow_non_finite=True
    )
    assert result == math.inf


def test_typed_parse_error_retains_decoded_response() -> None:
    transport = opened()
    transport.feed(b"not-a-number\n")
    with pytest.raises(ResponseParseError) as caught:
        ScpiClient(transport).query_float("MEAS?")
    assert caught.value.raw == "not-a-number"


def test_default_timeout_is_forwarded() -> None:
    transport = opened()
    client = ScpiClient(transport, timeout_s=2.5)
    client.write("*CLS")
    assert transport.operations[-1].timeout_s == 2.5


def test_per_call_timeout_overrides_default() -> None:
    transport = opened()
    client = ScpiClient(transport, timeout_s=2.5)
    client.write("*CLS", timeout_s=0.25)
    assert transport.operations[-1].timeout_s == 0.25


def test_none_timeout_defers_to_transport_without_client_default() -> None:
    transport = opened(timeout_s=7.0)
    ScpiClient(transport).write("*CLS")
    assert transport.operations[-1].timeout_s == 7.0


def test_one_operation_id_is_shared_by_both_transaction_halves() -> None:
    transport = opened()
    transport.feed(b"1\n")
    client = ScpiClient(transport)
    client.query("READ?")
    io_operations = [op for op in transport.operations if op.kind in {"write", "read"}]
    assert [op.operation_id for op in io_operations] == ["op-1", "op-1"]


def test_operation_ids_increment_once_per_public_operation() -> None:
    transport = opened()
    transport.feed(b"a")
    client = ScpiClient(transport)
    client.write_bytes(b"w")
    client.read_bytes(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=1))
    assert [op.operation_id for op in transport.operations[-2:]] == ["op-1", "op-2"]


def test_custom_operation_id_factory() -> None:
    transport = opened()
    ids = iter(["trace-a", "trace-b"])
    client = ScpiClient(transport, operation_id_factory=lambda: next(ids))
    client.write("A")
    client.write("B")
    assert [op.operation_id for op in transport.operations[-2:]] == ["trace-a", "trace-b"]


def test_operation_lock_is_reentrant() -> None:
    transport = opened()
    client = ScpiClient(transport)
    with client.operation_lock():
        client.write("A")
        with client.operation_lock():
            client.write("B")
    assert transport.written == b"A\nB\n"


def test_client_serializes_separate_operations() -> None:
    transport = opened()
    client = ScpiClient(transport)
    count = 8
    barrier = threading.Barrier(count)
    entered = threading.Event()
    release = threading.Event()
    factory_entries: list[str] = []
    entries_lock = threading.Lock()
    original_factory: Callable[[], str] = client._next_operation_id

    def blocking_factory() -> str:
        identifier = original_factory()
        with entries_lock:
            factory_entries.append(identifier)
        entered.set()
        release.wait(timeout=2)
        return identifier

    client._next_operation_id = blocking_factory

    def worker() -> None:
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(timeout=1)
        client.write("X")

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    assert entered.wait(timeout=1)
    # Only the lock holder may reach the factory before it is released.
    with entries_lock:
        assert len(factory_entries) == 1
    assert sum(thread.is_alive() for thread in threads) == count
    release.set()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert len({op.operation_id for op in transport.operations if op.kind == "write"}) == count


# -- binary blocks --------------------------------------------------------


def test_query_binary_block_returns_the_payload() -> None:
    transport = MockTransport()
    transport.open()
    transport.feed(b"#14ABCD\n")
    client = ScpiClient(transport)
    assert client.query_binary_block("CURVE?") == b"ABCD"
    assert transport.written == b"CURVE?\n"


def test_query_binary_block_consumes_the_terminator_by_default() -> None:
    """A leftover terminator would corrupt the next query."""
    transport = MockTransport()
    transport.open()
    transport.feed(b"#14ABCD\n")
    transport.feed(b"1.5\n")
    client = ScpiClient(transport)
    assert client.query_binary_block("CURVE?") == b"ABCD"
    assert client.query_float("MEAS?") == 1.5


def test_query_binary_block_can_leave_the_terminator() -> None:
    transport = MockTransport()
    transport.open()
    transport.feed(b"#14ABCD")
    client = ScpiClient(transport)
    assert client.query_binary_block("CURVE?", consume_terminator=False) == b"ABCD"


def test_query_binary_block_preserves_hostile_bytes() -> None:
    payload = bytes(range(256)) + b"  \t\x00\r\n  "
    transport = MockTransport()
    transport.open()
    transport.feed(b"#3" + str(len(payload)).encode() + payload + b"\n")
    client = ScpiClient(transport)
    assert client.query_binary_block("CURVE?") == payload


def test_query_binary_block_honors_maximum_size() -> None:
    transport = MockTransport()
    transport.open()
    transport.feed(b"#42048" + b"x" * 2048)
    client = ScpiClient(transport)
    with pytest.raises(ProtocolError):
        client.query_binary_block("CURVE?", maximum_size=16)


def test_write_binary_block_frames_the_command() -> None:
    transport = MockTransport()
    transport.open()
    ScpiClient(transport).write_binary_block("CURVE ", b"ABCD")
    assert transport.written == b"CURVE #14ABCD\n"


def test_write_binary_block_always_appends_the_terminator() -> None:
    """The payload ends with the terminator byte; it must not be mistaken for one."""
    transport = MockTransport()
    transport.open()
    ScpiClient(transport).write_binary_block("CURVE ", b"AB\n")
    assert transport.written == b"CURVE #13AB\n\n"


def test_write_binary_block_round_trips_through_the_decoder() -> None:
    payload = bytes(range(256))
    transport = MockTransport()
    transport.open()
    ScpiClient(transport).write_binary_block("DATA:ARB wave, ", payload)
    written = transport.written
    assert written.startswith(b"DATA:ARB wave, ")
    assert decode_definite_length_block(written[len(b"DATA:ARB wave, ") :]) == payload


def test_write_binary_block_is_one_transport_write() -> None:
    transport = MockTransport()
    transport.open()
    ScpiClient(transport).write_binary_block("CURVE ", b"ABCD")
    assert [op.kind for op in transport.operations if op.kind == "write"] == ["write"]
