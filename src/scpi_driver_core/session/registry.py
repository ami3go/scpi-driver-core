"""A registry of named sessions."""

from __future__ import annotations

import threading
from types import TracebackType

from scpi_driver_core.exceptions import ConfigurationError, _attach_cleanup_error
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
            existing = self._sessions.get(key)
            if existing is not None:
                if existing is session:
                    return
                if not replace:
                    raise ConfigurationError(
                        f"alias {key!r} is already registered; disconnect it first "
                        "or pass replace=True"
                    )
                # Replacement transfers ownership only after the old session
                # has released its transport successfully. A failed close
                # leaves the old registry entry intact and inspectable.
                existing.close()
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
        key = normalize_alias(alias)
        with self._lock:
            session = self.get(key)
            session.close()
            # Only successful cleanup transfers ownership out of the registry.
            if self._sessions.get(key) is session:
                del self._sessions[key]
                if self._active == key:
                    self._active = None

    def disconnect_all(self) -> None:
        with self._lock:
            first_error: BaseException | None = None
            additional_errors: list[BaseException] = []
            for key, session in list(self._sessions.items()):
                try:
                    session.close()
                except BaseException as exc:
                    if first_error is None:
                        first_error = exc
                    else:
                        additional_errors.append(exc)
                    continue
                if self._sessions.get(key) is session:
                    del self._sessions[key]
                    if self._active == key:
                        self._active = None

            if first_error is not None:
                attributes = getattr(first_error, "__dict__", None)
                if isinstance(attributes, dict) and additional_errors:
                    attributes["additional_cleanup_errors"] = tuple(additional_errors)
                add_note = getattr(first_error, "add_note", None)
                if callable(add_note):
                    for extra in additional_errors:
                        add_note(f"Additional registry cleanup failure: {extra!r}")
                raise first_error

    def __enter__(self) -> SessionRegistry:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc is None:
            self.disconnect_all()
            return
        try:
            self.disconnect_all()
        except BaseException as cleanup:
            _attach_cleanup_error(exc, cleanup)

    def _known(self) -> str:
        return ", ".join(sorted(self._sessions)) or "none"
