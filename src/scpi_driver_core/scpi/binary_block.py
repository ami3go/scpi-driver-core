"""IEEE-488.2 definite-length arbitrary block data."""

from __future__ import annotations

from typing import Final

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ProtocolError,
    TransportTimeoutError,
    UnsupportedOperationError,
)
from scpi_driver_core.transport.base import Transport
from scpi_driver_core.transport.models import ReadMode, ReadRequest

__all__ = [
    "DEFAULT_MAXIMUM_BLOCK_SIZE",
    "decode_definite_length_block",
    "encode_definite_length_block",
    "read_definite_length_block",
]

DEFAULT_MAXIMUM_BLOCK_SIZE: Final = 64 * 1024 * 1024
_MAX_LENGTH_DIGITS: Final = 9
_DIGITS: Final = frozenset(b"0123456789")


def encode_definite_length_block(payload: bytes) -> bytes:
    digits = str(len(payload)).encode("ascii")
    if len(digits) > _MAX_LENGTH_DIGITS:
        raise ConfigurationError(
            f"payload of {len(payload)} bytes needs more than {_MAX_LENGTH_DIGITS} length digits"
        )
    return b"#" + str(len(digits)).encode("ascii") + digits + payload


def _length_digit_count(prefix: bytes) -> int:
    if not prefix.startswith(b"#"):
        raise ProtocolError(f"block must start with '#', got {prefix[:8]!r}")
    if len(prefix) < 2:
        raise ProtocolError("block header is truncated after '#'")
    digit_count = prefix[1]
    if digit_count not in _DIGITS:
        raise ProtocolError(f"block digit count is not a digit: {prefix[:8]!r}")
    count = digit_count - ord("0")
    if count == 0:
        raise UnsupportedOperationError(
            "indefinite-length blocks ('#0') have no declared length and are not supported"
        )
    return count


def _declared_length(length_field: bytes, count: int, maximum_size: int) -> int:
    if len(length_field) < count:
        raise ProtocolError("block length field is truncated")
    if any(byte not in _DIGITS for byte in length_field):
        raise ProtocolError(f"block length field is not numeric: {length_field!r}")
    length = int(length_field)
    if length > maximum_size:
        raise ProtocolError(f"block declares {length} bytes, over maximum_size {maximum_size}")
    return length


def decode_definite_length_block(
    data: bytes,
    *,
    maximum_size: int = DEFAULT_MAXIMUM_BLOCK_SIZE,
    allow_trailing: bool = True,
) -> bytes:
    count = _length_digit_count(data)
    length = _declared_length(data[2 : 2 + count], count, maximum_size)
    header_length = 2 + count
    end = header_length + length
    available = len(data) - header_length
    if available < length:
        raise ProtocolError(f"block declares {length} payload bytes but only {available} arrived")
    if not allow_trailing and len(data) > end:
        raise ProtocolError(f"unexpected {len(data) - end} bytes after the block")
    return data[header_length:end]


def read_definite_length_block(
    transport: Transport,
    *,
    timeout_s: float | None = None,
    maximum_size: int = DEFAULT_MAXIMUM_BLOCK_SIZE,
    terminator: bytes | None = None,
    operation_id: str | None = None,
) -> bytes:
    """Read one definite-length block from an already serialized transport.

    Framing/protocol failures are intentionally not hidden or converted. The
    caller owns stream invalidation because it knows whether this function was
    entered as part of a larger transaction. A transport timeout remains a
    :class:`TransportTimeoutError`, preserving retry and health semantics.
    """
    if maximum_size <= 0:
        raise ConfigurationError(f"maximum_size must be positive, got {maximum_size}")

    def read_exactly(count: int, what: str) -> bytes:
        request = ReadRequest(mode=ReadMode.EXACT_LENGTH, length=count, maximum_size=max(count, 1))
        try:
            return transport.read(request, timeout_s=timeout_s, operation_id=operation_id)
        except TransportTimeoutError as exc:
            raise TransportTimeoutError(
                f"block {what} did not arrive: expected {count} bytes"
            ) from exc

    count = _length_digit_count(read_exactly(2, "header"))
    length = _declared_length(read_exactly(count, "length field"), count, maximum_size)
    payload = read_exactly(length, "payload") if length else b""
    if terminator:
        trailing = read_exactly(len(terminator), "terminator")
        if trailing != terminator:
            raise ProtocolError(f"expected terminator {terminator!r}, got {trailing!r}")
    return payload
