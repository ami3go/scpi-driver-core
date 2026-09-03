"""Confirmation guards for operations that should not happen by accident.

This is a mechanism, not a policy. The core does not decide that raw SCPI or
calibration needs guarding: a concrete driver creates a guard, chooses its
phrase, and calls :meth:`ConfirmationGuard.require_enabled` wherever it has
decided the risk warrants it.

State lives on the guard instance, which a driver holds per session. There is
no module-level registry and no ambient authorization, so enabling raw SCPI on
one instrument cannot silently unlock it on another. Distinct risks deserve
distinct guards: a calibration guard should be its own instance with its own
phrase, so confirming one never confirms the other.

A guard is a speed bump against mistakes, not a security boundary, and it is no
substitute for interlocks, fuses, or a wiring review.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from scpi_driver_core.exceptions import ConfigurationError, SafetyGuardError

__all__ = ["ConfirmationGuard"]


class ConfirmationGuard:
    """Requires an exact phrase before guarded operations are permitted.

    Args:
        phrase: what a caller must repeat to enable the guard. Matched exactly,
            including case and spacing, so it cannot be satisfied by a stray
            truthy value.
        name: how the guard describes itself in errors, such as
            ``"raw SCPI"``. Defaults to the phrase.

    Raises:
        ConfigurationError: if the phrase is empty, which would make the guard
            trivially satisfiable.
    """

    def __init__(self, phrase: str, *, name: str | None = None) -> None:
        if not phrase:
            raise ConfigurationError("phrase must not be empty")
        self._phrase = phrase
        self._name = name if name is not None else phrase
        self._enabled = False
        self._lock = threading.RLock()

    @property
    def name(self) -> str:
        return self._name

    @property
    def phrase(self) -> str:
        """The phrase required to enable this guard."""
        return self._phrase

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            return self._enabled

    def enable(self, phrase: str) -> None:
        """Unlock the guard.

        Raises:
            SafetyGuardError: if ``phrase`` does not match exactly.

        The phrase is not a secret and a driver is expected to document it.
        Its job is to make the action deliberate, the way typing a branch name
        does, not to withhold a credential.
        """
        with self._lock:
            if phrase != self._phrase:
                raise SafetyGuardError(
                    f"{self._name} guard was not enabled: the confirmation phrase did not match"
                )
            self._enabled = True

    def disable(self) -> None:
        """Lock the guard again. Safe to call when already locked."""
        with self._lock:
            self._enabled = False

    def require_enabled(self) -> None:
        """Assert the guard is unlocked, for a driver to call before a risky operation.

        Raises:
            SafetyGuardError: if the guard is locked.
        """
        with self._lock:
            if not self._enabled:
                raise SafetyGuardError(
                    f"{self._name} is guarded; enable it with its confirmation phrase first"
                )

    @contextmanager
    def enabled(self, phrase: str) -> Iterator[None]:
        """Unlock for the duration of a block, then restore the previous state.

        Preferable to a bare :meth:`enable` where the intent is to permit one
        sequence of operations, since the guard re-locks even if that sequence
        raises.
        """
        with self._lock:
            previous = self._enabled
            self.enable(phrase)
            try:
                yield
            finally:
                self._enabled = previous
