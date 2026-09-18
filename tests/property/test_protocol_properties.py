from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from scpi_driver_core.scpi import (
    ScpiTextCodec,
    decode_definite_length_block,
    encode_definite_length_block,
)


@given(payload=st.binary(max_size=16_384), trailing=st.binary(max_size=32))
def test_definite_length_block_round_trip_for_arbitrary_bytes(
    payload: bytes, trailing: bytes
) -> None:
    encoded = encode_definite_length_block(payload)

    assert decode_definite_length_block(encoded, allow_trailing=False) == payload
    assert decode_definite_length_block(encoded + trailing, allow_trailing=True) == payload


@given(
    text=st.text(
        alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
        max_size=256,
    )
)
def test_ascii_codec_round_trip_preserves_printable_text(text: str) -> None:
    codec = ScpiTextCodec()

    encoded = codec.encode_command(text)

    assert encoded.endswith(b"\n")
    assert codec.decode_response(encoded) == text
