"""Redaction hooks for protocol traces."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol, runtime_checkable

__all__ = ["PatternRedactor", "Redactor"]


@runtime_checkable
class Redactor(Protocol):
    def redact_command(self, command: str) -> str: ...

    def redact_response(self, response: str, *, command: str | None = None) -> str: ...


class PatternRedactor:
    """Regex redaction with optional query-aware full-response protection.

    ``sensitive_queries`` contains patterns matched against the command that
    produced a response. If one matches, the whole response is replaced. This
    covers secrets whose reply text carries no identifying prefix of its own.
    """

    def __init__(
        self,
        command_patterns: Iterable[str | re.Pattern[str]],
        *,
        response_patterns: Iterable[str | re.Pattern[str]] | None = None,
        sensitive_queries: Iterable[str | re.Pattern[str]] = (),
        placeholder: str = "***",
    ) -> None:
        self._command = [re.compile(pattern) for pattern in command_patterns]
        self._response = (
            self._command
            if response_patterns is None
            else [re.compile(pattern) for pattern in response_patterns]
        )
        self._sensitive_queries = [re.compile(pattern) for pattern in sensitive_queries]
        self._placeholder = placeholder

    def redact_command(self, command: str) -> str:
        return self._apply(self._command, command)

    def redact_response(self, response: str, *, command: str | None = None) -> str:
        if command is not None and any(
            pattern.search(command) for pattern in self._sensitive_queries
        ):
            return self._placeholder
        return self._apply(self._response, response)

    def _apply(self, patterns: list[re.Pattern[str]], text: str) -> str:
        for pattern in patterns:
            text = pattern.sub(self._substitute, text)
        return text

    def _substitute(self, match: re.Match[str]) -> str:
        if not match.groups():
            return self._placeholder
        start, end = match.span(1)
        return (
            match.group(0)[: start - match.start()]
            + self._placeholder
            + match.group(0)[end - match.start() :]
        )
