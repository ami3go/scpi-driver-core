"""Value types shared by every byte-oriented transport implementation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from scpi_driver_core.exceptions import ConfigurationError

__all__ = [
    "FlushDirection",
    "ReadMode",
    "ReadRequest",
    "ReplayPolicy",
    "TransportDescriptor",
    "TransportState",
    "WriteResult",
]


class TransportState(Enum):
    """Resource state of a transport, independent of communication health."""

    CREATED = "created"
    OPENING = "opening"
    OPEN = "open"
    FAULTED = "faulted"
    CLOSING = "closing"
    CLOSED = "closed"


@dataclass(frozen=True)
class TransportDescriptor:
    """Human-readable identity of a transport instance.

    ``kind`` is the transport family (``"tcp"``, ``"visa"``, ...), ``address``
    the resource it targets. Backend-specific detail belongs in ``metadata``
    rather than in additional fields.

    ``metadata`` is copied into a read-only mapping on construction, so a
    descriptor cannot be altered through the mapping the caller passed in.
    Descriptors are hashable; only ``kind`` and ``address`` contribute to the
    hash, while equality still compares ``metadata``.
    """

    kind: str
    address: str
    metadata: Mapping[str, str] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class ReadMode(Enum):
    """Explicit, bounded read semantics requested from a transport."""

    UNTIL_TERMINATOR = "until_terminator"
    EXACT_LENGTH = "exact_length"
    UP_TO_LENGTH = "up_to_length"
    AVAILABLE = "available"
    BACKEND_DEFINED_MESSAGE = "backend_defined_message"


_LENGTH_MODES = frozenset({ReadMode.EXACT_LENGTH, ReadMode.UP_TO_LENGTH})


@dataclass(frozen=True)
class ReadRequest:
    """A bounded read instruction.

    Every field must be applicable to the selected ``mode``. A field that the
    mode would ignore is rejected rather than silently dropped, so a request
    never reads differently from the way it looks.

    Raises:
        ConfigurationError: if the request would allow an unbounded read, or
            sets a field the selected mode does not use.
    """

    mode: ReadMode
    length: int | None = None
    terminator: bytes | None = None
    include_terminator: bool = False
    maximum_size: int = 1_048_576

    def __post_init__(self) -> None:
        if self.maximum_size <= 0:
            raise ConfigurationError(f"maximum_size must be positive, got {self.maximum_size}")

        if self.mode in _LENGTH_MODES:
            if self.length is None or self.length <= 0:
                raise ConfigurationError(
                    f"{self.mode.name} requires a positive length, got {self.length!r}"
                )
            if self.length > self.maximum_size:
                raise ConfigurationError(
                    f"length {self.length} exceeds maximum_size {self.maximum_size}"
                )
        elif self.length is not None:
            raise ConfigurationError(
                f"{self.mode.name} does not use length; maximum_size bounds the read"
            )

        if self.mode is ReadMode.UNTIL_TERMINATOR:
            if not self.terminator:
                raise ConfigurationError("UNTIL_TERMINATOR requires a non-empty terminator")
        else:
            if self.terminator is not None:
                raise ConfigurationError(f"{self.mode.name} does not use terminator")
            if self.include_terminator:
                raise ConfigurationError(f"{self.mode.name} does not use include_terminator")


@dataclass(frozen=True)
class WriteResult:
    """Outcome of a transport write."""

    bytes_written: int


class FlushDirection(Enum):
    """Which transport buffer(s) to discard."""

    INPUT = "input"
    OUTPUT = "output"
    BOTH = "both"


class ReplayPolicy(Enum):
    """Whether a transaction may be retried after a failure.

    ``SAFE`` must only be selected by a caller that knows the outbound message
    is idempotent; writes are never replayed automatically.
    """

    NEVER = "never"
    SAFE = "safe"
