"""A registry of named sessions.

Most of the source drivers let a test bench open several instruments of the
same model at once and address them by alias. This is that mechanism, with no
Robot Framework concepts in it: aliases are plain strings and the registry is
usable from a fixture, a notebook, or a script.

The registry never guesses. If more than one session exists and none has been
made active, asking for "the" session is an error rather than a coin flip,
because picking the wrong instrument can mean applying voltage to the wrong
bench.
"""

from __future__ import annotations

import threading

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.session.session import ScpiSession

__all__ = ["DEFAULT_ALIAS", "SessionRegistry", "normalize_alias"]

DEFAULT_ALIAS = "default"


def normalize_alias(alias: str) -> str:
    """Fold an alias to its canonical form.

    Surrounding whitespace is dropped and case is folded, so ``"PSU 1"`` and
    ``"psu 1"`` are the same session rather than two that silently shadow each
    other. Interior spacing is significant.

    Raises:
        ConfigurationError: if the alias is empty or only whitespace.
    """
    normalized = alias.strip().casefold()
    if not normalized:
        raise ConfigurationError("alias must not be empty")
    return normalized


class SessionRegistry:
    """Holds sessions by alias and tracks which one is active.

    The first session registered becomes active, which is deterministic rather
    than arbitrary. After that the active session only changes when
    :meth:`set_active` says so, or when the active one is removed.
    """

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

    # -- registration -----------------------------------------------------

    def register(self, alias: str, session: ScpiSession, *, replace: bool = False) -> None:
        """Add ``session`` under ``alias``.

        Args:
            replace: allow overwriting an existing alias. The displaced session
                is not closed, since the caller may still hold it; use
                :meth:`disconnect` to close and remove in one step.

        Raises:
            ConfigurationError: if the alias is taken and ``replace`` is false.
                Silently replacing would leave the previous transport open with
                nothing referencing it.
        """
        key = normalize_alias(alias)
        with self._lock:
            if key in self._sessions and not replace:
                raise ConfigurationError(
                    f"alias {key!r} is already registered; disconnect it first or pass replace=True"
                )
            self._sessions[key] = session
            if self._active is None:
                self._active = key

    def get(self, alias: str) -> ScpiSession:
        """Return the session registered as ``alias``.

        Raises:
            ConfigurationError: if nothing is registered under it.
        """
        key = normalize_alias(alias)
        with self._lock:
            try:
                return self._sessions[key]
            except KeyError:
                raise ConfigurationError(
                    f"no session registered as {key!r}; known aliases: {self._known()}"
                ) from None

    def remove(self, alias: str) -> ScpiSession:
        """Unregister ``alias`` and return its session, without closing it.

        Removing the active session leaves no active one, rather than promoting
        a survivor the caller did not choose.

        Raises:
            ConfigurationError: if nothing is registered under it.
        """
        key = normalize_alias(alias)
        with self._lock:
            session = self.get(key)
            del self._sessions[key]
            if self._active == key:
                self._active = None
            return session

    # -- the active session -----------------------------------------------

    def set_active(self, alias: str) -> None:
        """Make ``alias`` the active session.

        Raises:
            ConfigurationError: if nothing is registered under it.
        """
        key = normalize_alias(alias)
        with self._lock:
            self.get(key)
            self._active = key

    def get_active(self) -> ScpiSession:
        """Return the active session.

        Raises:
            ConfigurationError: if the registry is empty, or if the active
                session was removed and no replacement has been chosen. The
                registry will not pick one on the caller's behalf.
        """
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
        """The active alias, or ``None`` if none is chosen."""
        with self._lock:
            return self._active

    # -- inspection -------------------------------------------------------

    def list_aliases(self) -> list[str]:
        """Every registered alias, sorted so the order is reproducible."""
        with self._lock:
            return sorted(self._sessions)

    def list_sessions(self) -> list[ScpiSession]:
        """Every registered session, in the same order as :meth:`list_aliases`."""
        with self._lock:
            return [self._sessions[key] for key in sorted(self._sessions)]

    # -- disconnection ----------------------------------------------------

    def disconnect(self, alias: str) -> None:
        """Close the session registered as ``alias`` and unregister it.

        It is unregistered even if closing raises, so a transport that fails to
        close cannot strand its alias.

        Raises:
            ConfigurationError: if nothing is registered under it.
        """
        session = self.remove(alias)
        session.close()

    def disconnect_all(self) -> None:
        """Close and unregister every session.

        Every session is closed even if some fail, so one stuck instrument
        cannot leave the rest of a bench connected. The first failure is raised
        afterwards.
        """
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active = None

        first_error: BaseException | None = None
        for session in sessions:
            try:
                session.close()
            except BaseException as exc:  # noqa: BLE001 - re-raised once all are closed
                if first_error is None:
                    first_error = exc

        if first_error is not None:
            raise first_error

    def _known(self) -> str:
        return ", ".join(sorted(self._sessions)) or "none"
