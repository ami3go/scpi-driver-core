from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ProtocolError,
    UnsupportedOperationError,
)
from scpi_driver_core.scpi.binary_block import (
    decode_definite_length_block,
    encode_definite_length_block,
    read_definite_length_block,
)
from scpi_driver_core.transport import MockTransport

#: Bytes that would be destroyed by any strip() on the way through.
HOSTILE = b"  \t\r\n\x00 leading and trailing \x00\r\n\t  "


def transport_with(*chunks: bytes) -> MockTransport:
    transport = MockTransport()
    transport.open()
    for chunk in chunks:
        transport.feed(chunk)
    return transport


# -- encoding -------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"", b"#10"),
        (b"A", b"#11A"),
        (b"0123456789", b"#210" + b"0123456789"),
        (b"x" * 100, b"#3100" + b"x" * 100),
    ],
)
def test_encode(payload: bytes, expected: bytes) -> None:
    assert encode_definite_length_block(payload) == expected


def test_encode_preserves_hostile_bytes() -> None:
    encoded = encode_definite_length_block(HOSTILE)
    assert encoded == b"#2" + str(len(HOSTILE)).encode() + HOSTILE
    assert decode_definite_length_block(encoded) == HOSTILE


def test_encode_round_trips_every_byte_value() -> None:
    payload = bytes(range(256))
    assert decode_definite_length_block(encode_definite_length_block(payload)) == payload


def test_encode_large_block() -> None:
    payload = b"\x00" * 1_000_000
    encoded = encode_definite_length_block(payload)
    assert encoded.startswith(b"#71000000")
    assert decode_definite_length_block(encoded, maximum_size=2_000_000) == payload


def test_encode_rejects_a_payload_needing_ten_length_digits() -> None:
    class Huge:
        def __len__(self) -> int:
            return 10**10

    with pytest.raises(ConfigurationError, match="length digits"):
        encode_definite_length_block(Huge())  # type: ignore[arg-type]


# -- decoding -------------------------------------------------------------


def test_decode_zero_length() -> None:
    assert decode_definite_length_block(b"#10") == b""


def test_decode_ignores_trailing_terminator_by_default() -> None:
    assert decode_definite_length_block(b"#14ABCD\n") == b"ABCD"


def test_decode_can_forbid_trailing_bytes() -> None:
    with pytest.raises(ProtocolError, match="after the block"):
        decode_definite_length_block(b"#14ABCD\n", allow_trailing=False)


def test_decode_accepts_an_exact_block_when_trailing_forbidden() -> None:
    assert decode_definite_length_block(b"#14ABCD", allow_trailing=False) == b"ABCD"


@pytest.mark.parametrize(
    "data",
    [b"", b"ABCD", b"1234", b"@14ABCD"],
)
def test_decode_rejects_a_missing_hash(data: bytes) -> None:
    with pytest.raises(ProtocolError, match="start with"):
        decode_definite_length_block(data)


def test_decode_rejects_a_lone_hash() -> None:
    with pytest.raises(ProtocolError, match="truncated"):
        decode_definite_length_block(b"#")


def test_decode_rejects_a_non_digit_count() -> None:
    with pytest.raises(ProtocolError, match="digit count"):
        decode_definite_length_block(b"#XABCD")


def test_decode_rejects_a_non_numeric_length_field() -> None:
    with pytest.raises(ProtocolError, match="not numeric"):
        decode_definite_length_block(b"#2AB12345")


def test_decode_rejects_a_truncated_length_field() -> None:
    with pytest.raises(ProtocolError, match="length field is truncated"):
        decode_definite_length_block(b"#41")


def test_decode_rejects_a_truncated_payload() -> None:
    with pytest.raises(ProtocolError, match="only 2 arrived"):
        decode_definite_length_block(b"#14AB")


def test_decode_rejects_an_oversized_declaration() -> None:
    with pytest.raises(ProtocolError, match="maximum_size"):
        decode_definite_length_block(b"#42048" + b"x" * 2048, maximum_size=1024)


def test_decode_rejects_the_indefinite_form() -> None:
    """'#0' is legal IEEE-488.2 but unbounded, so it is refused, not guessed at."""
    with pytest.raises(UnsupportedOperationError, match="indefinite"):
        decode_definite_length_block(b"#0ABCD")


# -- reading from a transport ---------------------------------------------


def test_read_block() -> None:
    transport = transport_with(b"#14ABCD")
    assert read_definite_length_block(transport) == b"ABCD"


def test_read_block_arriving_in_fragments() -> None:
    """The header may be split across reads, as a stream transport allows."""
    transport = transport_with(b"#", b"1", b"4", b"AB", b"CD")
    assert read_definite_length_block(transport) == b"ABCD"


def test_read_zero_length_block() -> None:
    transport = transport_with(b"#10")
    assert read_definite_length_block(transport) == b""


def test_read_preserves_hostile_bytes() -> None:
    transport = transport_with(encode_definite_length_block(HOSTILE))
    assert read_definite_length_block(transport) == HOSTILE


def test_read_consumes_the_terminator_when_asked() -> None:
    transport = transport_with(b"#14ABCD\n")
    assert read_definite_length_block(transport, terminator=b"\n") == b"ABCD"
    assert transport.pending_bytes == 0


def test_read_leaves_the_terminator_when_not_asked() -> None:
    transport = transport_with(b"#14ABCD\n")
    assert read_definite_length_block(transport) == b"ABCD"
    assert transport.pending_bytes == 1


def test_read_rejects_a_wrong_terminator() -> None:
    transport = transport_with(b"#14ABCD;")
    with pytest.raises(ProtocolError, match="expected terminator"):
        read_definite_length_block(transport, terminator=b"\n")


def test_read_detects_a_truncated_payload() -> None:
    transport = transport_with(b"#18AB")
    with pytest.raises(ProtocolError, match="payload did not arrive"):
        read_definite_length_block(transport)


def test_read_detects_a_missing_terminator() -> None:
    transport = transport_with(b"#14ABCD")
    with pytest.raises(ProtocolError, match="terminator did not arrive"):
        read_definite_length_block(transport, terminator=b"\n")


def test_read_detects_a_truncated_header() -> None:
    transport = transport_with(b"#")
    with pytest.raises(ProtocolError, match="header did not arrive"):
        read_definite_length_block(transport)


def test_read_rejects_a_missing_hash() -> None:
    transport = transport_with(b"XY1234")
    with pytest.raises(ProtocolError, match="start with"):
        read_definite_length_block(transport)


def test_read_rejects_a_non_digit_count() -> None:
    transport = transport_with(b"#XABCD")
    with pytest.raises(ProtocolError, match="digit count"):
        read_definite_length_block(transport)


def test_read_rejects_a_non_numeric_length_field() -> None:
    transport = transport_with(b"#2AB")
    with pytest.raises(ProtocolError, match="not numeric"):
        read_definite_length_block(transport)


def test_read_rejects_the_indefinite_form() -> None:
    transport = transport_with(b"#0ABCD")
    with pytest.raises(UnsupportedOperationError, match="indefinite"):
        read_definite_length_block(transport)


def test_read_rejects_an_oversized_declaration_before_reading_payload() -> None:
    """The bound is enforced from the header, so the payload is never pulled in."""
    transport = transport_with(b"#42048" + b"x" * 2048)
    with pytest.raises(ProtocolError, match="maximum_size"):
        read_definite_length_block(transport, maximum_size=1024)
    assert transport.pending_bytes == 2048


def test_read_rejects_a_nonpositive_maximum_size() -> None:
    with pytest.raises(ConfigurationError):
        read_definite_length_block(transport_with(b"#10"), maximum_size=0)


def test_read_forwards_the_operation_id() -> None:
    transport = transport_with(b"#14ABCD")
    read_definite_length_block(transport, operation_id="op-7")
    assert {op.operation_id for op in transport.operations if op.kind == "read"} == {"op-7"}
