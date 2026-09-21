"""A named SCPI session: one client, one transport, one connection lifetime."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import replace
from types import TracebackType

from scpi_driver_core.exceptions import (
    ConfigurationError,
    IdentityError,
    ScpiDriverError,
    SessionClosedError,
    TransportError,
)
from scpi_driver_core.models import Identity
from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.scpi.ieee488 import Ieee4882
from scpi_driver_core.session.health import SessionHealth
from scpi_driver_core.tracing.events import TraceContext
from scpi_driver_core.tracing.observer import Tracer
from scpi_driver_core.transport.base import Transport
from scpi_driver_core.transport.models import TransportState

__all__ = ["DEFAULT_HEALTH_QUERY", "ScpiSession"]

DEFAULT_HEALTH_QUERY = "*IDN?"


class ScpiSession:
    """Own one instrument connection under a stable alias."""

    def __init__(
        self,
        alias: str,
        client: ScpiClient,
        *,
        health_query: str = DEFAULT_HEALTH_QUERY,
        communication_timeout_s: float | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self._alias = alias
        self._client = client
        self._health_query = health_query
        self._communication_timeout_s = communication_timeout_s
        self._tracer = tracer
        self._ieee488 = Ieee4882(client)
        self._health = SessionHealth()
        self._generation = 0
        self._identity: Identity | None = None
        self._lock = threading.RLock()
        self._validate_identity: Callable[[Identity], None] | None = None
        self._probe_on_recover = False
        self._client.add_outcome_listener(self._on_outcome)

    @property
    def alias(self) -> str:
        return self._alias

    @property
    def client(self) -> ScpiClient:
        return self._client

    @property
    def transport(self) -> Transport:
        return self._client.transport

    @property
    def ieee488(self) -> Ieee4882:
        return self._ieee488

    @property
    def tracer(self) -> Tracer | None:
        return self._tracer

    @property
    def health(self) -> SessionHealth:
        """Return a snapshot whose connected flag always reflects transport state."""
        with self._lock:
            return replace(self._health, connected=self.is_connected)

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    @property
    def communication_timeout_s(self) -> float | None:
        with self._lock:
            return self._communication_timeout_s

    def set_communication_timeout(self, timeout_s: float | None) -> None:
        if timeout_s is not None and (not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ConfigurationError(
                f"communication timeout must be finite and positive, got {timeout_s!r}"
            )
        with self._lock:
            self._communication_timeout_s = timeout_s

    def operation_lock(self) -> AbstractContextManager[None]:
        """The client's lock, for making a sequence of operations indivisible."""
        return self._client.operation_lock()

    @contextmanager
    def _session_operation(self) -> Iterator[None]:
        """Canonical cross-layer lock order: client, then session."""
        with self._client.operation_lock(), self._lock:
            yield

    @property
    def is_connected(self) -> bool:
        """Whether the transport resource is open; this never waits for device I/O."""
        return self.transport.state is TransportState.OPEN

    def open(
        self,
        *,
        probe: bool = False,
        validate_identity: Callable[[Identity], None] | None = None,
    ) -> None:
        with self._session_operation():
            self._reopen_transport()
            try:
                if probe:
                    self._probe()
                if validate_identity is not None:
                    validate_identity(self.get_identity(refresh=True))
            except BaseException:
                with suppress(Exception):
                    self.transport.close()
                self._identity = None
                self._health.record_disconnected()
                raise
            self._probe_on_recover = probe
            self._validate_identity = validate_identity

    def _reopen_transport(self) -> None:
        self.transport.open()
        self._generation += 1
        self._identity = None
        self._health.record_connected()
        self._publish_trace_context()

    def recover_if_faulted(self) -> None:
        """Recover only a connection that failed during I/O.

        ``CREATED`` and ``CLOSED`` represent caller intent, not a transient
        transport failure, so retry machinery must never silently reopen them.
        The same probe and identity validator used by the successful explicit
        :meth:`open` are re-applied after every recovery.
        """
        with self._session_operation():
            state = self.transport.state
            if state is TransportState.OPEN:
                return
            if state is not TransportState.FAULTED:
                raise SessionClosedError(
                    f"session {self._alias!r} is {state.name}; call open() explicitly"
                )
            self._reopen_transport()
            try:
                if self._probe_on_recover:
                    self._probe()
                if self._validate_identity is not None:
                    self._validate_identity(self.get_identity(refresh=True))
            except BaseException:
                with suppress(Exception):
                    self.transport.close()
                self._identity = None
                self._health.record_disconnected()
                raise

    def close(self) -> None:
        with self._session_operation():
            try:
                self.transport.close()
            finally:
                self._identity = None
                self._health.record_disconnected()

    def __enter__(self) -> ScpiSession:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def check_communication(self, *, timeout_s: float | None = None) -> bool:
        with self._session_operation():
            try:
                self._probe(timeout_s=timeout_s)
            except ScpiDriverError:
                return False
            return True

    def _publish_trace_context(self) -> None:
        context = TraceContext(
            session_alias=self._alias,
            session_generation=self._generation,
        )
        setter = getattr(self.transport, "set_context", None)
        if callable(setter):
            setter(context)
        elif self._tracer is not None:
            self._tracer.set_context(context)

    def _on_outcome(self, error: ScpiDriverError | None) -> None:
        """Feed normal client traffic into health without changing lock order."""
        with self._lock:
            if error is None:
                self._health.record_success()
            elif isinstance(error, TransportError):
                self._health.record_failure(error)

    def _probe(self, *, timeout_s: float | None = None) -> None:
        effective = self._communication_timeout_s if timeout_s is None else timeout_s
        self._client.query(self._health_query, timeout_s=effective)

    def get_identity(self, *, refresh: bool = False) -> Identity:
        with self._session_operation():
            if self._identity is None or refresh:
                try:
                    self._identity = self._ieee488.identify()
                except IdentityError as exc:
                    self._health.record_protocol_failure(exc)
                    raise
            return self._identity
