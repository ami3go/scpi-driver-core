import struct

import pytest

from keysight_n6700.scpi import (
    format_channel_list,
    parse_binary_real_array,
    parse_error,
    parse_idn,
    parse_multi_binary_real_arrays,
)


def block(values):
    payload = struct.pack(">" + "d" * len(values), *values)
    return b"#" + str(len(str(len(payload)))).encode() + str(len(payload)).encode() + payload


def test_channel_list():
    assert format_channel_list(1) == "(@1)"
    assert format_channel_list([1, 3, 4]) == "(@1,3,4)"
    assert format_channel_list(range(1, 5)) == "(@1:4)"
    with pytest.raises(ValueError):
        format_channel_list(5)


def test_idn_parse_compatibility():
    assert parse_idn("KEYSIGHT TECHNOLOGIES,N6700B,MY1,B.1").model == "N6700B"
    assert parse_idn("AGILENT TECHNOLOGIES,N6700B,MY1,B.1").manufacturer.startswith("AGILENT")
    assert parse_idn("HEWLETT-PACKARD,N6700B,MY1,B.1").manufacturer.startswith("HEWLETT")


def test_parse_error_record():
    err = parse_error('-113,"Undefined header"')
    assert err.code == -113
    assert err.message == "Undefined header"


def test_binary_blocks():
    data = block([1.0, 2.0])
    assert parse_binary_real_array(data) == [1.0, 2.0]
    multi = data + b"," + block([3.0])
    assert parse_multi_binary_real_arrays(multi, 2) == [[1.0, 2.0], [3.0]]
