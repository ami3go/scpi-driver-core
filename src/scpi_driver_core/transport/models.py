"""Value types shared by every byte-oriented transport implementation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from scpi_driver_core.exceptions import ConfigurationError

__all__ = [
    "FlushDirection",
    "FrozenMetadata",
    "ReadMode",
    "ReadRequest",
    "ReplayPolicy",
    "TransportDescriptor",
    "TransportState",
    "WriteResult",
]


class TransportState(Enum):
    CREATED = "created"
    OPENING = "opening"
    OPEN = "open"
    FAULTED = "faulted"
    CLOSING = "closing"
    CLOSED = "closed"


class FrozenMetadata(Mapping[str, str]):
    """Immutable, hashable, pickle/deepcopy-safe transport metadata."""

    __slots__ = ("_data",)
    _data: dict[str, str]

    def __init__(self, data: Mapping[str, str] | None = None) -> None:
        object.__setattr__(self, "_data", dict(data or {}))

    def __getitem__(self, key: str) -> str:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __hash__(self) -> int:
        return hash(frozenset(self._data.items()))

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Mapping) and dict(self) == dict(other)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("FrozenMetadata is immutable")

    def __reduce__(self) -> tuple[Any, ...]:
        return (FrozenMetadata, (self._data,))

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenMetadata:
        return self

    def __repr__(self) -> str:
        return f"FrozenMetadata({self._data!r})"


@dataclass(frozen=True)
class TransportDescriptor:
    """Human-readable identity of a transport instance."""

    kind: str
    address: str
    metadata: Mapping[str, str] = field(default_factory=dict, hash=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", FrozenMetadata(self.metadata))


class ReadMode(Enum):
    UNTIL_TERMINATOR = "until_terminator"
    EXACT_LENGTH = "exact_length"
    UP_TO_LENGTH = "up_to_length"
    AVAILABLE = "available"
    BACKEND_DEFINED_MESSAGE = "backend_defined_message"


_LENGTH_MODES = frozenset({ReadMode.EXACT_LENGTH, ReadMode.UP_TO_LENGTH})


@dataclass(frozen=True)
class ReadRequest:
    """A bounded read instruction with no ignored fields."""

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
    bytes_written: int


class FlushDirection(Enum):
    INPUT = "input"
    OUTPUT = "output"
    BOTH = "both"


class ReplayPolicy(Enum):
    NEVER = "never"
    SAFE = "safe"
