"""Value types shared across the SCPI, session, and tracing layers."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Identity", "ScpiError", "SelfTestResult"]


@dataclass(frozen=True)
class Identity:
    """A parsed ``*IDN?`` reply.

    The core parses; deciding whether a manufacturer, model, or firmware
    revision is acceptable belongs to the concrete driver.
    """

    manufacturer: str
    model: str
    serial_number: str | None
    firmware_version: str | None
    raw: str


@dataclass(frozen=True)
class ScpiError:
    """One entry from an instrument's error queue.

    Whether ``code`` counts as "no error" is a policy of the error queue, not
    of this record: most instruments use 0, but the set is configurable.
    """

    code: int
    message: str
    raw: str


@dataclass(frozen=True)
class SelfTestResult:
    """The outcome of ``*TST?``.

    IEEE-488.2 defines 0 as success and any non-zero value as a failure whose
    meaning is manufacturer-specific, so ``code`` is kept verbatim for a
    concrete driver to interpret.
    """

    code: int
    raw: str

    @property
    def passed(self) -> bool:
        return self.code == 0
