"""A registry of named sessions."""

from __future__ import annotations

import threading
from types import TracebackType

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.session.session import ScpiSession

__all__ = ["DEFAULT_ALIAS", "SessionRegistry", "normalize_alias"]

DEFAULT_ALIAS = "default"


def normalize_alias(alias: str) -> str:
    normalized = alias.strip().casefold()
    if not normalized:
        raise ConfigurationError("alias must not be empty")
    return normalized


class SessionRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, ScpiSession] = {}
        self._active: str | None = None
        self._lock = threading.RLock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def __contains__(self, alias: str) -> bool:
        with self._lock:
            return normalize_alias(alias) in self._sessions

    def register(self, alias: str, session: ScpiSession, *, replace: bool = False) -> None:
        """Register exactly once under the session's own normalized alias."""
        key = normalize_alias(alias)
        session_key = normalize_alias(session.alias)
        if session_key != key:
            raise ConfigurationError(
                f"alias {alias!r} does not match session.alias {session.alias!r}"
            )
        with self._lock:
            if any(
                existing is session for known, existing in self._sessions.items() if known != key
            ):
                raise ConfigurationError("this session is already registered under another alias")
            if key in self._sessions and not replace:
                raise ConfigurationError(
                    f"alias {key!r} is already registered; disconnect it first or pass replace=True"
                )
            self._sessions[key] = session
            if self._active is None:
                self._active = key

    def get(self, alias: str) -> ScpiSession:
        key = normalize_alias(alias)
        with self._lock:
            try:
                return self._sessions[key]
            except KeyError:
                raise ConfigurationError(
                    f"no session registered as {key!r}; known aliases: {self._known()}"
                ) from None

    def remove(self, alias: str) -> ScpiSession:
        key = normalize_alias(alias)
        with self._lock:
            session = self.get(key)
            del self._sessions[key]
            if self._active == key:
                self._active = None
            return session

    def set_active(self, alias: str) -> None:
        key = normalize_alias(alias)
        with self._lock:
            self.get(key)
            self._active = key

    def get_active(self) -> ScpiSession:
        with self._lock:
            if self._active is None:
                if not self._sessions:
                    raise ConfigurationError("no sessions are registered")
                raise ConfigurationError(
                    "no active session; call set_active with one of: " + self._known()
                )
            return self._sessions[self._active]

    @property
    def active_alias(self) -> str | None:
        with self._lock:
            return self._active

    def list_aliases(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions)

    def list_sessions(self) -> list[ScpiSession]:
        with self._lock:
            return [self._sessions[key] for key in sorted(self._sessions)]

    def disconnect(self, alias: str) -> None:
        session = self.remove(alias)
        session.close()

    def disconnect_all(self) -> None:
        with self._lock:
            sessions = list(dict.fromkeys(self._sessions.values()))
            self._sessions.clear()
            self._active = None
        first_error: BaseException | None = None
        for session in sessions:
            try:
                session.close()
            except BaseException as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def __enter__(self) -> SessionRegistry:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.disconnect_all()

    def _known(self) -> str:
        return ", ".join(sorted(self._sessions)) or "none"
