"""The instrument error queue, and the policy for consulting it.

``SYST:ERR?`` pops one entry and answers ``0,"No error"`` once the queue is
empty. Draining therefore means querying repeatedly until a no-error code
appears, which is exactly the loop every driver in the source set had written
for itself.

Nothing here runs on its own. Reading the queue is itself instrument traffic,
and doing it after every operation would double the command count and clear
errors a driver may have wanted to inspect. A concrete driver opts in through
:class:`ScpiExecutionPolicy`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from scpi_driver_core.exceptions import ConfigurationError, ScpiErrorQueueError
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
    """When to consult the error queue automatically.

    Both checks are off by default. Turning one on makes every write or query
    cost an extra round trip, which is worth it while bringing a driver up and
    usually not in a tight measurement loop.
    """

    check_error_queue_after_write: bool = False
    check_error_queue_after_query: bool = False

    @property
    def checks_anything(self) -> bool:
        return self.check_error_queue_after_write or self.check_error_queue_after_query


@dataclass
class ScpiErrorQueue:
    """Reads and drains an instrument's error queue.

    Args:
        client: the client to query on.
        command: the query to use. Most instruments accept ``SYST:ERR?``, but
            some spell it differently, so it is configurable rather than
            assumed.
        no_error_codes: codes meaning "queue empty". Conventionally just 0.
        maximum_entries: how many entries a single drain will pop before giving
            up, so a device stuck reporting errors cannot loop forever.

    Raises:
        ConfigurationError: if the command is empty, the no-error set is empty,
            or ``maximum_entries`` is not positive.
    """

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
        """Whether ``error`` is the instrument's way of saying the queue is empty."""
        return error.code in self.no_error_codes

    def read_one(self, *, timeout_s: float | None = None) -> ScpiError:
        """Pop and parse a single entry.

        A no-error reply is returned like any other, not swallowed, so a caller
        can tell an empty queue from a populated one.

        Raises:
            ResponseParseError: if the reply is not ``code,"message"``.
        """
        return parse_scpi_error(self.client.query(self.command, timeout_s=timeout_s))

    def drain(
        self, *, max_entries: int | None = None, timeout_s: float | None = None
    ) -> list[ScpiError]:
        """Pop entries until the queue reports empty.

        The whole drain is held under the client's operation lock, so a
        concurrent caller cannot consume half of it.

        Args:
            max_entries: override the configured bound for this drain.
            timeout_s: bound for each individual query.

        Returns:
            The real errors, in the order the instrument reported them. Empty
            when there were none. The terminating no-error entry is not
            included.

        Raises:
            ScpiErrorQueueError: if the queue never reports empty within the
                bound, which means the instrument is producing errors faster
                than they can be read, or does not use a no-error code this
                queue knows about.
        """
        limit = self.maximum_entries if max_entries is None else max_entries
        if limit <= 0:
            raise ConfigurationError(f"max_entries must be positive, got {limit}")

        collected: list[ScpiError] = []
        with self.client.operation_lock():
            for _ in range(limit):
                entry = self.read_one(timeout_s=timeout_s)
                if self.is_no_error(entry):
                    return collected
                collected.append(entry)

        raise ScpiErrorQueueError(
            f"error queue did not empty within {limit} entries; last was {collected[-1].raw!r}"
        )

    def raise_if_errors(
        self, *, max_entries: int | None = None, timeout_s: float | None = None
    ) -> None:
        """Drain, and raise if the instrument had anything to report.

        Raises:
            ScpiErrorQueueError: if the queue held any entries. The message
                lists all of them, since the first is often a consequence of a
                command several steps earlier.
        """
        errors = self.drain(max_entries=max_entries, timeout_s=timeout_s)
        if errors:
            raise ScpiErrorQueueError(_describe(errors))


def _describe(errors: Sequence[ScpiError]) -> str:
    listed = "; ".join(f"{error.code}: {error.message}" for error in errors)
    noun = "error" if len(errors) == 1 else "errors"
    return f"instrument reported {len(errors)} {noun}: {listed}"
