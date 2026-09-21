"""Confirmation guards for operations that should not happen by accident.

A guard is a deliberate-action mechanism, not a security boundary. Its lock
protects only guard state and is never held while user code runs.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from scpi_driver_core.exceptions import ConfigurationError, SafetyGuardError

__all__ = ["ConfirmationGuard"]


class ConfirmationGuard:
    """Requires an exact phrase before guarded operations are permitted.

    Permanent :meth:`enable` state is shared intentionally. Scoped
    :meth:`enabled` state is thread-local: one worker's temporary calibration
    window must not unlock another worker. :meth:`disable` increments a global
    epoch, revoking every open scoped window immediately without waiting for
    those blocks to exit.
    """

    def __init__(self, phrase: str, *, name: str | None = None) -> None:
        if not phrase:
            raise ConfigurationError("phrase must not be empty")
        self._phrase = phrase
        self._name = name if name is not None else phrase
        self._enabled = False
        self._epoch = 0
        self._lock = threading.Lock()
        self._local = threading.local()

    @property
    def name(self) -> str:
        return self._name

    @property
    def phrase(self) -> str:
        return self._phrase

    def _local_scope(self) -> tuple[int, int]:
        depth = int(getattr(self._local, "depth", 0))
        epoch = int(getattr(self._local, "epoch", -1))
        return depth, epoch

    def _scoped_enabled(self, epoch: int) -> bool:
        depth, local_epoch = self._local_scope()
        return depth > 0 and local_epoch == epoch

    @property
    def is_enabled(self) -> bool:
        with self._lock:
            globally_enabled = self._enabled
            epoch = self._epoch
        return globally_enabled or self._scoped_enabled(epoch)

    def enable(self, phrase: str) -> None:
        """Unlock globally after an exact phrase match."""
        if phrase != self._phrase:
            raise SafetyGuardError(
                f"{self._name} guard was not enabled: the confirmation phrase did not match"
            )
        with self._lock:
            self._enabled = True

    def disable(self) -> None:
        """Lock globally and revoke all currently open scoped windows."""
        with self._lock:
            self._enabled = False
            self._epoch += 1

    def require_enabled(self) -> None:
        """Fail fast unless globally or locally enabled for the current epoch."""
        with self._lock:
            globally_enabled = self._enabled
            epoch = self._epoch
        if not globally_enabled and not self._scoped_enabled(epoch):
            raise SafetyGuardError(
                f"{self._name} is guarded; enable it with its confirmation phrase first"
            )

    @contextmanager
    def enabled(self, phrase: str) -> Iterator[None]:
        """Temporarily enable only the current thread, without holding a lock."""
        if phrase != self._phrase:
            raise SafetyGuardError(
                f"{self._name} guard was not enabled: the confirmation phrase did not match"
            )
        with self._lock:
            epoch = self._epoch
        depth, local_epoch = self._local_scope()
        if depth and local_epoch != epoch:
            depth = 0
        self._local.depth = depth + 1
        self._local.epoch = epoch
        try:
            yield
        finally:
            current_depth, current_epoch = self._local_scope()
            if current_epoch == epoch and current_depth > 0:
                self._local.depth = current_depth - 1
                if self._local.depth == 0:
                    self._local.epoch = -1
