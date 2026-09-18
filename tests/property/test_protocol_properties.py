from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scpi_driver_core.exceptions import ProtocolError
from scpi_driver_core.scpi import (
    ScpiTextCodec,
    decode_definite_length_block,
    encode_definite_length_block,
)

pytestmark = pytest.mark.property

_ASCII_TEXT = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    max_size=256,
)


@given(payload=st.binary(max_size=16_384), trailing=st.binary(max_size=32))
def test_definite_length_block_round_trip_for_arbitrary_bytes(
    payload: bytes, trailing: bytes
) -> None:
    encoded = encode_definite_length_block(payload)

    assert decode_definite_length_block(encoded, allow_trailing=False) == payload
    assert decode_definite_length_block(encoded + trailing, allow_trailing=True) == payload


@given(payload=st.binary(min_size=1, max_size=4_096), data=st.data())
def test_truncated_binary_blocks_are_never_accepted(payload: bytes, data: st.DataObject) -> None:
    encoded = encode_definite_length_block(payload)
    length_digits = encoded[1] - ord("0")
    header_length = 2 + length_digits
    cut = data.draw(st.integers(min_value=header_length, max_value=len(encoded) - 1))

    with pytest.raises(ProtocolError):
        decode_definite_length_block(encoded[:cut])


@given(payload=st.binary(min_size=1, max_size=4_096))
def test_binary_block_maximum_size_is_always_enforced(payload: bytes) -> None:
    encoded = encode_definite_length_block(payload)

    with pytest.raises(ProtocolError):
        decode_definite_length_block(encoded, maximum_size=len(payload) - 1)


@given(text=_ASCII_TEXT)
def test_ascii_codec_round_trip_preserves_printable_text(text: str) -> None:
    codec = ScpiTextCodec()
    encoded = codec.encode_command(text)

    assert encoded.endswith(b"\n")
    assert codec.decode_response(encoded) == text


@given(text=_ASCII_TEXT, already_terminated=st.booleans())
def test_command_terminator_is_appended_exactly_once(text: str, already_terminated: bool) -> None:
    codec = ScpiTextCodec(command_terminator=b"\n")
    command = text + ("\n" if already_terminated else "")

    assert codec.encode_command(command) == text.encode("ascii") + b"\n"


@given(text=_ASCII_TEXT, trailing_spaces=st.integers(min_value=0, max_value=16))
def test_response_codec_removes_only_exact_terminator(
    text: str, trailing_spaces: int
) -> None:
    codec = ScpiTextCodec(response_terminator=b"\r\n")
    response = (text + (" " * trailing_spaces)).encode("ascii") + b"\r\n"

    assert codec.decode_response(response) == text + (" " * trailing_spaces)
