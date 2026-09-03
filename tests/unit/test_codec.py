from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ProtocolError,
    ResponseParseError,
)
from scpi_driver_core.scpi import ScpiTextCodec


def test_defaults() -> None:
    codec = ScpiTextCodec()
    assert codec.encoding == "ascii"
    assert codec.command_terminator == b"\n"
    assert codec.response_terminator == b"\n"


def test_rejects_unknown_encoding() -> None:
    with pytest.raises(ConfigurationError):
        ScpiTextCodec(encoding="definitely-not-an-encoding")


@pytest.mark.parametrize("size", [0, -1])
def test_rejects_nonpositive_limits(size: int) -> None:
    with pytest.raises(ConfigurationError):
        ScpiTextCodec(maximum_command_size=size)
    with pytest.raises(ConfigurationError):
        ScpiTextCodec(maximum_response_size=size)


# -- encoding -------------------------------------------------------------


def test_appends_terminator() -> None:
    assert ScpiTextCodec().encode_command("*IDN?") == b"*IDN?\n"


def test_does_not_double_an_existing_terminator() -> None:
    assert ScpiTextCodec().encode_command("*IDN?\n") == b"*IDN?\n"


def test_multibyte_terminator_is_appended_once() -> None:
    codec = ScpiTextCodec(command_terminator=b"\r\n")
    assert codec.encode_command("*IDN?") == b"*IDN?\r\n"
    assert codec.encode_command("*IDN?\r\n") == b"*IDN?\r\n"


def test_supports_no_terminator() -> None:
    codec = ScpiTextCodec(command_terminator=b"")
    assert codec.encode_command("*IDN?") == b"*IDN?"


def test_rejects_command_that_cannot_be_encoded() -> None:
    with pytest.raises(ConfigurationError):
        ScpiTextCodec().encode_command("MEAS:VOLT? µ")


def test_non_ascii_encoding_is_honored() -> None:
    codec = ScpiTextCodec(encoding="utf-8")
    assert codec.encode_command("µ") == "µ".encode() + b"\n"


def test_rejects_oversized_command() -> None:
    codec = ScpiTextCodec(maximum_command_size=8)
    with pytest.raises(ConfigurationError):
        codec.encode_command("X" * 32)


def test_command_size_limit_counts_the_terminator() -> None:
    codec = ScpiTextCodec(maximum_command_size=4)
    assert codec.encode_command("ABC") == b"ABC\n"
    with pytest.raises(ConfigurationError):
        codec.encode_command("ABCD")


# -- decoding -------------------------------------------------------------


def test_strips_exactly_one_trailing_terminator() -> None:
    assert ScpiTextCodec().decode_response(b"1.5\n") == "1.5"


def test_leaves_a_second_terminator_in_place() -> None:
    assert ScpiTextCodec().decode_response(b"1.5\n\n") == "1.5\n"


def test_tolerates_a_missing_terminator() -> None:
    assert ScpiTextCodec().decode_response(b"1.5") == "1.5"


def test_does_not_strip_a_different_terminator() -> None:
    codec = ScpiTextCodec(response_terminator=b"\r\n")
    assert codec.decode_response(b"1.5\n") == "1.5\n"


def test_preserves_interior_and_trailing_whitespace() -> None:
    """Only the configured terminator is removed; padding is the parsers' problem."""
    assert ScpiTextCodec().decode_response(b"  1.5  \n") == "  1.5  "


def test_preserves_trailing_carriage_return() -> None:
    assert ScpiTextCodec().decode_response(b"1.5\r\n") == "1.5\r"


def test_supports_unterminated_responses() -> None:
    codec = ScpiTextCodec(response_terminator=None)
    assert codec.decode_response(b"1.5\n") == "1.5\n"


def test_empty_response_decodes_to_empty_string() -> None:
    assert ScpiTextCodec().decode_response(b"") == ""


def test_bare_terminator_decodes_to_empty_string() -> None:
    assert ScpiTextCodec().decode_response(b"\n") == ""


def test_rejects_undecodable_response_and_keeps_the_bytes() -> None:
    with pytest.raises(ResponseParseError) as excinfo:
        ScpiTextCodec().decode_response(b"\xff\xfe\n")
    assert excinfo.value.raw == b"\xff\xfe\n"


def test_replacement_errors_can_be_opted_into() -> None:
    codec = ScpiTextCodec(decode_errors="replace")
    assert codec.decode_response(b"\xff\n") == "�"


def test_rejects_oversized_response() -> None:
    codec = ScpiTextCodec(maximum_response_size=8)
    with pytest.raises(ProtocolError):
        codec.decode_response(b"X" * 32)


def test_round_trip_of_a_realistic_exchange() -> None:
    codec = ScpiTextCodec()
    assert codec.encode_command("MEAS:VOLT:DC?") == b"MEAS:VOLT:DC?\n"
    assert codec.decode_response(b"+1.04858000E+00\n") == "+1.04858000E+00"


# -- block command framing ------------------------------------------------


def test_encode_block_command_frames_prefix_block_and_terminator() -> None:
    assert ScpiTextCodec().encode_block_command("CURVE ", b"#14ABCD") == b"CURVE #14ABCD\n"


def test_encode_block_command_always_terminates() -> None:
    """A block ending in the terminator byte must still get its own."""
    codec = ScpiTextCodec()
    assert codec.encode_block_command("CURVE ", b"#13AB\n") == b"CURVE #13AB\n\n"


def test_encode_block_command_honors_an_empty_terminator() -> None:
    codec = ScpiTextCodec(command_terminator=b"")
    assert codec.encode_block_command("CURVE ", b"#11A") == b"CURVE #11A"


def test_encode_block_command_rejects_an_unencodable_prefix() -> None:
    with pytest.raises(ConfigurationError, match="prefix"):
        ScpiTextCodec().encode_block_command("CURVE µ ", b"#11A")


def test_encode_block_command_bounds_the_prefix() -> None:
    with pytest.raises(ConfigurationError, match="maximum_command_size"):
        ScpiTextCodec(maximum_command_size=4).encode_block_command("CURVE ", b"#11A")


def test_encode_block_command_does_not_bound_the_payload() -> None:
    """A waveform upload dwarfs any sane text-command limit; that is the caller's call."""
    codec = ScpiTextCodec(maximum_command_size=16)
    framed = codec.encode_block_command("CURVE ", b"#6100000" + b"x" * 100000)
    assert len(framed) > 100000
