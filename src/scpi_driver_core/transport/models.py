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


@dataclass(frozen=True)
class ReadRequest:
    """A bounded read instruction.

    Raises:
        ConfigurationError: if the requested combination of fields would allow
            an unbounded or undefined read.
    """

    mode: ReadMode
    length: int | None = None
    terminator: bytes | None = None
    include_terminator: bool = False
    maximum_size: int = 1_048_576

    def __post_init__(self) -> None:
        if self.maximum_size <= 0:
            raise ConfigurationError(f"maximum_size must be positive, got {self.maximum_size}")
        if self.mode in (ReadMode.EXACT_LENGTH, ReadMode.UP_TO_LENGTH):
            if self.length is None or self.length <= 0:
                raise ConfigurationError(
                    f"{self.mode.name} requires a positive length, got {self.length!r}"
                )
            if self.length > self.maximum_size:
                raise ConfigurationError(
                    f"length {self.length} exceeds maximum_size {self.maximum_size}"
                )
        if self.mode is ReadMode.UNTIL_TERMINATOR and not self.terminator:
            raise ConfigurationError("UNTIL_TERMINATOR requires a non-empty terminator")


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
