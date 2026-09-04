"""Pure codec tests: known bytes + known preamble -> known decoded values.

No transport or simulator involved — task §13.1 items 2 and 3.
"""

from __future__ import annotations

import struct

import pytest

from tbs1000c.codec import decode_samples, parse_curve_response, parse_idn, scale_waveform
from tbs1000c.exceptions import Tbs1000cProtocolError
from tbs1000c.models import WaveformPreamble


def _preamble(**overrides) -> WaveformPreamble:
    base = dict(
        bit_nr=8,
        bn_fmt="RI",
        byt_nr=1,
        encdg="BINARY",
        nr_pt=4,
        record_length=4,
        wfid="test",
        x_increment=1.0,
        x_zero=0.0,
        x_unit="s",
        y_multiplier=2.0,
        y_offset=1.0,
        y_zero=0.5,
        y_unit="V",
    )
    base.update(overrides)
    return WaveformPreamble(**base)


def test_decode_binary_curve_known_values():
    # Four signed 8-bit codes: 0, 1, -1, 10.
    raw_codes = [0, 1, -1, 10]
    payload = struct.pack(">4b", *raw_codes)
    block = f"#1{len(payload)}".encode("ascii") + payload

    extracted = parse_curve_response(block)
    assert extracted == payload

    preamble = _preamble()
    codes = decode_samples(extracted, preamble)
    assert codes == raw_codes

    time_s, volts = scale_waveform(codes, preamble)
    # volts[i] = (code - y_offset) * y_multiplier + y_zero
    assert volts == [
        (0 - 1.0) * 2.0 + 0.5,
        (1 - 1.0) * 2.0 + 0.5,
        (-1 - 1.0) * 2.0 + 0.5,
        (10 - 1.0) * 2.0 + 0.5,
    ]
    # time_s[i] = i * x_increment + x_zero
    assert time_s == [0.0, 1.0, 2.0, 3.0]


def test_decode_ascii_curve_known_values():
    ascii_response = b"0,1,-1,10"
    extracted = parse_curve_response(ascii_response)

    preamble = _preamble()
    codes = decode_samples(extracted, preamble)
    assert codes == [0, 1, -1, 10]

    _time_s, volts = scale_waveform(codes, preamble)
    assert volts[0] == pytest.approx(-1.5)
    assert volts[3] == pytest.approx(18.5)


def test_16bit_binary_curve_decodes_correctly():
    raw_codes = [0, 32000, -32000, 1234]
    payload = struct.pack(">4h", *raw_codes)
    block = f"#1{len(payload)}".encode("ascii") + payload

    preamble = _preamble(byt_nr=2, nr_pt=4)
    codes = decode_samples(parse_curve_response(block), preamble)
    assert codes == raw_codes


def test_byte_count_mismatch_raises_not_truncates():
    """task §13.1 item 3: a short/misaligned CURVe? payload must raise, never silently truncate."""

    preamble = _preamble(nr_pt=4, byt_nr=1)
    short_payload = struct.pack(">2b", 1, 2)  # only 2 points, preamble expects 4

    with pytest.raises(Tbs1000cProtocolError):
        decode_samples(short_payload, preamble)


def test_byte_count_not_multiple_of_width_raises():
    preamble = _preamble(byt_nr=2, nr_pt=2)
    misaligned = b"\x00\x01\x02"  # 3 bytes, not a multiple of 2

    with pytest.raises(Tbs1000cProtocolError):
        decode_samples(misaligned, preamble)


def test_truncated_ieee_block_header_raises():
    with pytest.raises(Tbs1000cProtocolError):
        parse_curve_response(b"#")


def test_block_declares_more_bytes_than_received_raises():
    with pytest.raises(Tbs1000cProtocolError):
        parse_curve_response(b"#15\x00\x01")  # declares 5 bytes, only 2 present


def test_parse_idn_real_manual_example():
    raw = "TEKTRONIX,TBS 1072C,CU10100,CF:91.1CT FV:v2015-12-10_01-00-59rootfs; FPGA:v1.21;"
    identity = parse_idn(raw)
    assert identity.manufacturer == "TEKTRONIX"
    assert identity.model == "TBS 1072C"
    assert identity.serial == "CU10100"
    assert "FPGA" in identity.firmware
    assert identity.raw == raw
