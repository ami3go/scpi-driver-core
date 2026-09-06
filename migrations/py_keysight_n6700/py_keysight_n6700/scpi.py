"""SCPI formatting and parsing helpers.

All command formatting/parsing is centralized here to avoid ad-hoc SCPI strings.

Migrated onto ``scpi-driver-core``. The generic parsers, identity, error-queue
entries, CSV and IEEE-488.2 definite-length blocks, now come from the core.
What stays is what is actually specific to this instrument: the ``(@1:4)``
channel-list syntax, the manufacturer whitelist, the comma-separated multi-block
framing the N6700 uses for multi-channel digitize, and the REAL32/REAL64
unpacking of its datalog payloads.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Iterable, Sequence
from typing import Literal

from scpi_driver_core.exceptions import ResponseParseError
from scpi_driver_core.scpi import (
    decode_definite_length_block,
    parse_csv,
    parse_float,
    parse_identity,
    parse_scpi_error,
)

from .exceptions import N6700CommandError
from .types import InstrumentIdentity, ScpiErrorRecord

SUPPORTED_MANUFACTURERS = {
    "KEYSIGHT TECHNOLOGIES",
    "AGILENT TECHNOLOGIES",
    "HEWLETT-PACKARD",
}


def format_bool(value: bool) -> str:
    return "ON" if value else "OFF"


def format_float(value: float) -> str:
    return f"{value:.12g}"


def _flatten_channels(channels: int | Sequence[int] | range) -> list[int]:
    if isinstance(channels, int):
        return [channels]
    return list(channels)


def format_channel_list(channels: int | Sequence[int] | range) -> str:
    values = _flatten_channels(channels)
    if not values:
        raise ValueError("at least one channel is required")
    for ch in values:
        if ch < 1 or ch > 4:
            raise ValueError(f"invalid N6700 channel: {ch}")
    # Preserve explicit order. Use range shorthand only for a range object.
    if isinstance(channels, range) and values == list(range(values[0], values[-1] + 1)):
        return f"(@{values[0]}:{values[-1]})"
    return "(@" + ",".join(str(ch) for ch in values) + ")"


def parse_channel_list(text: str) -> list[int]:
    m = re.search(r"\(@([^)]*)\)", text)
    if not m:
        return []
    body = m.group(1).strip()
    if not body:
        return []
    result: list[int] = []
    for part in body.split(","):
        part = part.strip()
        if ":" in part:
            start, end = [int(x.strip()) for x in part.split(":", 1)]
            result.extend(range(start, end + 1))
        else:
            result.append(int(part))
    return result


def parse_csv_floats(response: str) -> list[float]:
    """Split a CSV reply into floats, using the core's CSV-aware parser."""
    return [parse_float(item) for item in parse_csv(response) if item.strip()]


def parse_csv_strings(response: str) -> list[str]:
    """Split a CSV reply into strings; the N6700 quotes some of its fields."""
    return [item.strip().strip('"') for item in parse_csv(response)]


def parse_idn(response: str) -> InstrumentIdentity:
    """Parse ``*IDN?`` and enforce this driver's manufacturer policy.

    The core parses the reply; deciding which manufacturers this driver will
    talk to is a device-specific judgement and stays here.
    """
    try:
        identity = parse_identity(response)
    except Exception as exc:
        raise N6700CommandError(f"invalid *IDN? response: {response!r}") from exc
    if identity.serial_number is None or identity.firmware_version is None:
        raise N6700CommandError(f"invalid *IDN? response: {response!r}")
    manufacturer = " ".join(identity.manufacturer.upper().split())
    if manufacturer not in SUPPORTED_MANUFACTURERS:
        raise N6700CommandError(
            f"unsupported manufacturer in *IDN? response: {identity.manufacturer!r}"
        )
    return InstrumentIdentity(
        identity.manufacturer,
        identity.model,
        identity.serial_number,
        identity.firmware_version,
    )


def parse_error(response: str) -> ScpiErrorRecord:
    """Parse a ``SYST:ERR?`` entry, tolerating the shapes this driver has met."""
    raw = response.strip()
    if not raw:
        return ScpiErrorRecord(0, "No error", raw)
    if "," not in raw:
        return ScpiErrorRecord(0, raw.strip().strip('"'), raw)
    try:
        error = parse_scpi_error(raw)
    except ResponseParseError as exc:
        raise N6700CommandError(f"invalid SYST:ERR? response: {response!r}") from exc
    return ScpiErrorRecord(error.code, error.message.strip().strip('"'), raw)


def parse_ieee488_definite_block(data: bytes) -> bytes:
    """Extract a definite-length block payload, via the core implementation."""
    try:
        return decode_definite_length_block(data)
    except Exception as exc:
        raise N6700CommandError(str(exc)) from exc


def split_ieee488_blocks(data: bytes) -> list[bytes]:
    """Split comma-separated definite-length blocks: <block>,<block>,..."""
    blocks: list[bytes] = []
    idx = 0
    n = len(data)
    while idx < n:
        if data[idx : idx + 1] != b"#":
            raise N6700CommandError("expected binary block")
        if idx + 2 > n or not chr(data[idx + 1]).isdigit():
            raise N6700CommandError("malformed block header")
        n_digits = int(chr(data[idx + 1]))
        header_len = 2 + n_digits
        if idx + header_len > n:
            raise N6700CommandError("truncated block header")
        payload_len = int(data[idx + 2 : idx + header_len].decode("ascii"))
        end = idx + header_len + payload_len
        if end > n:
            raise N6700CommandError("truncated block payload")
        blocks.append(data[idx + header_len : end])
        idx = end
        if idx == n:
            break
        if data[idx : idx + 1] != b",":
            raise N6700CommandError("missing comma between binary blocks")
        idx += 1
    return blocks


def parse_binary_real_array(
    data: bytes,
    byte_order: Literal["normal", "swapped"] = "normal",
    *,
    width: Literal[4, 8] = 8,
) -> list[float]:
    payload = parse_ieee488_definite_block(data) if data.startswith(b"#") else data
    if len(payload) % width:
        raise N6700CommandError("binary REAL payload length is not a multiple of element width")
    endian = ">" if byte_order == "normal" else "<"
    code = "f" if width == 4 else "d"
    count = len(payload) // width
    return list(struct.unpack(f"{endian}{count}{code}", payload))


def parse_multi_binary_real_arrays(
    data: bytes,
    channel_count: int,
    byte_order: Literal["normal", "swapped"] = "normal",
    *,
    width: Literal[4, 8] = 8,
) -> list[list[float]]:
    blocks = split_ieee488_blocks(data)
    if len(blocks) != channel_count:
        raise N6700CommandError(f"expected {channel_count} binary blocks, received {len(blocks)}")
    endian = ">" if byte_order == "normal" else "<"
    code = "f" if width == 4 else "d"
    arrays: list[list[float]] = []
    for payload in blocks:
        if len(payload) % width:
            raise N6700CommandError("binary REAL payload length is not a multiple of element width")
        count = len(payload) // width
        arrays.append(list(struct.unpack(f"{endian}{count}{code}", payload)))
    return arrays


def iter_channel_values(channels: Sequence[int], response: str) -> Iterable[tuple[int, float]]:
    values = parse_csv_floats(response)
    if len(values) != len(channels):
        raise N6700CommandError(
            f"query returned {len(values)} values for {len(channels)} requested channels"
        )
    return zip(channels, values, strict=True)
