"""The instrument error queue, and the policy for consulting it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ResponseParseError,
    ScpiErrorQueueError,
)
from scpi_driver_core.models import ScpiError
from scpi_driver_core.scpi.parsers import parse_scpi_error

if TYPE_CHECKING:
    from scpi_driver_core.scpi.client import ScpiClient

__all__ = [
    "DEFAULT_ERROR_QUERY",
    "DEFAULT_MAXIMUM_ENTRIES",
    "DEFAULT_NO_ERROR_CODES",
    "ScpiErrorQueue",
    "ScpiExecutionPolicy",
]

DEFAULT_ERROR_QUERY: Final = "SYST:ERR?"
DEFAULT_NO_ERROR_CODES: Final = frozenset({0})
DEFAULT_MAXIMUM_ENTRIES: Final = 32


@dataclass(frozen=True)
class ScpiExecutionPolicy:
    """When to consult the error queue automatically after successful traffic."""

    check_error_queue_after_write: bool = False
    check_error_queue_after_query: bool = False

    @property
    def checks_anything(self) -> bool:
        return self.check_error_queue_after_write or self.check_error_queue_after_query


@dataclass
class ScpiErrorQueue:
    client: ScpiClient
    command: str = DEFAULT_ERROR_QUERY
    no_error_codes: frozenset[int] = field(default=DEFAULT_NO_ERROR_CODES)
    maximum_entries: int = DEFAULT_MAXIMUM_ENTRIES

    def __post_init__(self) -> None:
        if not self.command:
            raise ConfigurationError("command must not be empty")
        self.no_error_codes = frozenset(self.no_error_codes)
        if not self.no_error_codes:
            raise ConfigurationError("no_error_codes must contain at least one code")
        if self.maximum_entries <= 0:
            raise ConfigurationError(
                f"maximum_entries must be positive, got {self.maximum_entries}"
            )

    def is_no_error(self, error: ScpiError) -> bool:
        return error.code in self.no_error_codes

    def read_one(self, *, timeout_s: float | None = None) -> ScpiError:
        return parse_scpi_error(self.client.query(self.command, timeout_s=timeout_s))

    def drain(
        self, *, max_entries: int | None = None, timeout_s: float | None = None
    ) -> list[ScpiError]:
        """Pop entries until empty, preserving every popped entry on failure."""
        limit = self.maximum_entries if max_entries is None else max_entries
        if limit <= 0:
            raise ConfigurationError(f"max_entries must be positive, got {limit}")

        collected: list[ScpiError] = []
        with self.client.operation_lock():
            for _ in range(limit):
                reply = self.client.query(self.command, timeout_s=timeout_s)
                try:
                    entry = parse_scpi_error(reply)
                except ResponseParseError as exc:
                    raise ScpiErrorQueueError(
                        f"unparsable error-queue reply {reply!r}",
                        errors=collected,
                        complete=False,
                    ) from exc
                if self.is_no_error(entry):
                    return collected
                collected.append(entry)

        raise ScpiErrorQueueError(
            f"error queue did not empty within {limit} entries: {_describe(collected)}",
            errors=collected,
            complete=False,
        )

    def raise_if_errors(
        self, *, max_entries: int | None = None, timeout_s: float | None = None
    ) -> None:
        errors = self.drain(max_entries=max_entries, timeout_s=timeout_s)
        if errors:
            raise ScpiErrorQueueError(_describe(errors), errors=errors, complete=True)


def _describe(errors: Sequence[ScpiError]) -> str:
    listed = "; ".join(f"{error.code}: {error.message}" for error in errors)
    noun = "error" if len(errors) == 1 else "errors"
    return f"instrument reported {len(errors)} {noun}: {listed}"
