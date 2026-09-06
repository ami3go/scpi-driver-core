"""SCPI response parsing helpers."""

from __future__ import annotations

import math
import re
from typing import Iterable

from .exceptions import ProtocolError

_FLOAT_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?$")
_INT_RE = re.compile(r"^[+-]?\d+$")


def clean_response(response: str | bytes) -> str:
    """Decode and strip a SCPI response terminator and surrounding whitespace."""
    if isinstance(response, bytes):
        try:
            response = response.decode("ascii")
        except UnicodeDecodeError as exc:
            raise ProtocolError("Response is not valid ASCII") from exc
    return response.strip().strip("\x00")


def parse_float(response: str | bytes, *, command: str) -> float:
    """Parse SCPI NRf numeric response including signs and scientific notation."""
    text = clean_response(response)
    if not _FLOAT_RE.match(text):
        raise ProtocolError(f"Malformed numeric response for {command!r}: {text!r}")
    value = float(text)
    if not math.isfinite(value):
        raise ProtocolError(f"Non-finite numeric response for {command!r}: {text!r}")
    return value


def parse_int(response: str | bytes, *, command: str) -> int:
    """Parse SCPI integer response."""
    text = clean_response(response)
    if not _INT_RE.match(text):
        raise ProtocolError(f"Malformed integer response for {command!r}: {text!r}")
    return int(text)


def parse_bool(response: str | bytes, *, command: str) -> bool:
    """Parse common SCPI boolean response values."""
    text = clean_response(response).upper()
    if text in {"1", "ON", "TRUE"}:
        return True
    if text in {"0", "OFF", "FALSE"}:
        return False
    raise ProtocolError(f"Malformed boolean response for {command!r}: {text!r}")


def parse_csv_floats(response: str | bytes, *, command: str) -> list[float]:
    """Parse comma-separated numeric response."""
    text = clean_response(response)
    if not text:
        raise ProtocolError(f"Empty CSV response for {command!r}")
    return [parse_float(part.strip(), command=command) for part in text.split(",")]


def parse_csv_ints(response: str | bytes, *, command: str) -> list[int]:
    """Parse comma-separated integer response."""
    text = clean_response(response)
    if not text:
        raise ProtocolError(f"Empty CSV response for {command!r}")
    return [parse_int(part.strip(), command=command) for part in text.split(",")]


def format_bool(value: bool | int) -> str:
    """Format a Python boolean-like value as SCPI 0/1."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if value in (0, 1):
        return str(int(value))
    raise ProtocolError(f"Cannot format non-boolean value as SCPI bool: {value!r}")


def format_channel_list(channels: Iterable[int]) -> str:
    """Format a validated channel list as SCPI (@1,2,3)."""
    return "(@" + ",".join(str(ch) for ch in channels) + ")"
