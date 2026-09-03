"""Redaction hooks for protocol traces.

SCPI traffic is not automatically safe to persist. Calibration security codes,
instrument passwords, and private network settings all travel as ordinary
commands, and a JSONL audit file usually outlives the test run that produced
it.

The core provides the hook and applies it consistently. Deciding what is
sensitive is the concrete driver's job, because only it knows which of its
commands carry secrets.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

__all__ = ["PatternRedactor", "Redactor"]


@runtime_checkable
class Redactor(Protocol):
    """Rewrites trace payloads to remove sensitive content."""

    def redact_command(self, command: str) -> str:
        """Return ``command`` with anything sensitive replaced."""
        ...

    def redact_response(self, response: str) -> str:
        """Return ``response`` with anything sensitive replaced."""
        ...


class PatternRedactor:
    """Replaces every regex match with a placeholder.

    A convenience for the common case, not a policy: it redacts exactly the
    patterns a driver hands it and nothing else.

    Args:
        command_patterns: applied to outbound commands.
        response_patterns: applied to inbound responses. Defaults to the
            command patterns, since a value echoed back is as sensitive as the
            one sent.
        placeholder: what each match is replaced with.

    A pattern's first capturing group, if it has one, is what gets replaced,
    so ``CAL:SEC:CODE (\\S+)`` keeps the command visible and hides only the
    code.
    """

    def __init__(
        self,
        command_patterns: Iterable[str | re.Pattern[str]],
        *,
        response_patterns: Iterable[str | re.Pattern[str]] | None = None,
        placeholder: str = "***",
    ) -> None:
        self._command = [re.compile(pattern) for pattern in command_patterns]
        self._response = (
            self._command
            if response_patterns is None
            else [re.compile(pattern) for pattern in response_patterns]
        )
        self._placeholder = placeholder

    def redact_command(self, command: str) -> str:
        return self._apply(self._command, command)

    def redact_response(self, response: str) -> str:
        return self._apply(self._response, response)

    def _apply(self, patterns: list[re.Pattern[str]], text: str) -> str:
        for pattern in patterns:
            text = pattern.sub(self._substitute, text)
        return text

    def _substitute(self, match: re.Match[str]) -> str:
        if not match.groups():
            return self._placeholder
        # Keep everything outside the first group, so the command stays legible.
        start, end = match.span(1)
        return (
            match.group(0)[: start - match.start()]
            + self._placeholder
            + match.group(0)[end - match.start() :]
        )
