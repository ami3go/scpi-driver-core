"""IEEE-488.2 definite-length arbitrary block data.

The wire format is ``#<n><length><payload>``, where ``n`` is a single digit
giving how many digits the decimal ``length`` occupies. ``#42048`` introduces
2048 payload bytes.

Every payload byte is preserved exactly. Nothing here strips, trims, or decodes
anything: a waveform capture is full of bytes that look like whitespace and
null, and treating them as framing would silently corrupt the data. This is why
binary transfers bypass the text codec entirely.

The indefinite-length form ``#0`` is recognized and rejected rather than
mis-parsed, since its payload runs until the message ends and cannot be bounded
in advance.
"""

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

#: A definite-length header can carry at most nine length digits.
_MAX_LENGTH_DIGITS: Final = 9

_DIGITS: Final = frozenset(b"0123456789")


def encode_definite_length_block(payload: bytes) -> bytes:
    """Wrap ``payload`` in a definite-length block header.

    An empty payload encodes as ``#10``, which is the conventional zero-length
    block rather than a special case.

    Raises:
        ConfigurationError: if the payload is too large for the nine-digit
            length field, which no real instrument would accept anyway.
    """
    digits = str(len(payload)).encode("ascii")
    if len(digits) > _MAX_LENGTH_DIGITS:
        raise ConfigurationError(
            f"payload of {len(payload)} bytes needs more than {_MAX_LENGTH_DIGITS} length digits"
        )
    return b"#" + str(len(digits)).encode("ascii") + digits + payload


def _length_digit_count(prefix: bytes) -> int:
    """Validate ``#<n>`` and return ``n``, the number of length digits to follow.

    Shared by both the in-memory and streaming paths so the two cannot drift
    into disagreeing about what a valid header is.
    """
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
    """Validate the decimal length field and check it against ``maximum_size``."""
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
    """Extract the payload from a complete block already held in memory.

    Args:
        data: the block, optionally followed by a terminator or other trailing
            bytes.
        maximum_size: reject a block declaring more than this many payload bytes.
        allow_trailing: whether bytes after the payload are tolerated. Set it
            false to require that ``data`` is exactly one block.

    Raises:
        ProtocolError: for a malformed header, a declared length over
            ``maximum_size``, a payload shorter than declared, or unexpected
            trailing bytes when ``allow_trailing`` is false.
        UnsupportedOperationError: for the indefinite-length form.
    """
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
    """Read one definite-length block from ``transport``.

    The header is read a few bytes at a time so the declared length is known
    before any payload is requested, which is what keeps the read bounded. The
    payload is then taken as one exact-length read, so no byte is inspected or
    altered on the way through.

    Args:
        transport: an open transport positioned at the start of a block.
        timeout_s: bound for each underlying read; ``None`` uses the
            transport's default.
        maximum_size: reject a block declaring more payload than this.
        terminator: consumed and verified after the payload when given.
            Instruments usually append one, and leaving it unread would
            corrupt the next response.
        operation_id: correlation identifier passed to the transport.

    Raises:
        ProtocolError: for a malformed header, an over-large declared length, a
            truncated payload, or a missing/mismatched terminator.
        UnsupportedOperationError: for the indefinite-length form.
    """
    if maximum_size <= 0:
        raise ConfigurationError(f"maximum_size must be positive, got {maximum_size}")

    def read_exactly(count: int, what: str) -> bytes:
        request = ReadRequest(mode=ReadMode.EXACT_LENGTH, length=count, maximum_size=max(count, 1))
        try:
            return transport.read(request, timeout_s=timeout_s, operation_id=operation_id)
        except TransportTimeoutError as exc:
            raise ProtocolError(f"block {what} did not arrive: expected {count} bytes") from exc

    count = _length_digit_count(read_exactly(2, "header"))
    length = _declared_length(read_exactly(count, "length field"), count, maximum_size)

    payload = read_exactly(length, "payload") if length else b""

    if terminator:
        trailing = read_exactly(len(terminator), "terminator")
        if trailing != terminator:
            raise ProtocolError(f"expected terminator {terminator!r}, got {trailing!r}")

    return payload
