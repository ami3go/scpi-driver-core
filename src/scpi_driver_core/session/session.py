"""A named SCPI session: one client, one transport, one connection lifetime."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress

from scpi_driver_core.exceptions import ConfigurationError, ScpiDriverError
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
    """One instrument connection, owned under an alias.

    The session owns the transport lifetime and caches what belongs to a single
    connection: the identity the instrument reported, its health, and a
    generation counter that changes on every reconnect.

    Nothing instrument-specific belongs here. Measurement state, output
    settings, and channel maps live in the concrete driver; this class only
    knows how to be connected.

    Args:
        alias: the name this session is known by.
        client: the SCPI client, which owns the protocol layer.
        health_query: the query used to test responsiveness. ``*IDN?`` suits
            most instruments, but a driver may pick something cheaper or safer.
        communication_timeout_s: bound for this session's own traffic.
        tracer: kept in step with this session's alias and generation, so trace
            records spanning a reconnect cannot be read as one connection.
    """

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

    # -- identity of the session itself -----------------------------------

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
        """The IEEE-488.2 helpers bound to this session's client."""
        return self._ieee488

    @property
    def tracer(self) -> Tracer | None:
        """The tracer whose context this session maintains, if any."""
        return self._tracer

    @property
    def health(self) -> SessionHealth:
        return self._health

    @property
    def generation(self) -> int:
        """Increments on every successful open.

        A reader holding a value from before a reconnect can tell that the
        connection it observed is not the current one, so cached state from the
        old connection is never mistaken for fresh.
        """
        with self._lock:
            return self._generation

    @property
    def communication_timeout_s(self) -> float | None:
        """Bound applied to this session's own traffic, such as health checks.

        ``None`` defers to the client, which in turn defers to the transport.
        A driver adjusts this for an instrument that is simply slow, without
        having to rebuild the client.
        """
        with self._lock:
            return self._communication_timeout_s

    def set_communication_timeout(self, timeout_s: float | None) -> None:
        """Set the bound used for this session's own traffic.

        Raises:
            ConfigurationError: if the timeout is not finite and positive.
        """
        if timeout_s is not None and (not math.isfinite(timeout_s) or timeout_s <= 0):
            raise ConfigurationError(
                f"communication timeout must be finite and positive, got {timeout_s!r}"
            )
        with self._lock:
            self._communication_timeout_s = timeout_s

    def operation_lock(self) -> object:
        """The client's lock, for making a sequence of operations indivisible."""
        return self._client.operation_lock()

    @contextmanager
    def _session_operation(self) -> Iterator[None]:
        """Acquire cross-layer locks in the single safe order: client, then session.

        Retry recovery is invoked while :meth:`ScpiClient.query` already holds
        the client operation lock. Session methods that acquired ``self._lock``
        first and then entered the client inverted that order and could deadlock
        against recovery on another thread. Keeping one lock order preserves
        operation serialization without an AB/BA cycle.
        """
        with self._client.operation_lock(), self._lock:
            yield

    # -- connection state, without touching the instrument ----------------

    @property
    def is_connected(self) -> bool:
        """Whether the transport holds its resource.

        Never performs device I/O, so it cannot block and cannot be mistaken
        for evidence that the instrument is responding. Use
        :meth:`check_communication` for that.
        """
        return self.transport.state is TransportState.OPEN

    # -- lifecycle --------------------------------------------------------

    def open(
        self,
        *,
        probe: bool = False,
        validate_identity: Callable[[Identity], None] | None = None,
    ) -> None:
        """Open the transport and start a new connection generation.

        A hardware connection that fails stays failed: nothing here falls back
        to a simulated transport, because a test that silently passes against a
        fake instrument is worse than one that fails.

        Args:
            probe: run the health query once the transport is open, so a
                connection that cannot actually talk fails here rather than at
                the first measurement.
            validate_identity: given the parsed ``*IDN?`` reply so a concrete
                driver can reject the wrong instrument. Raising from it aborts
                the connection. The core never judges identity itself.

        Raises:
            ScpiDriverError: whatever the transport, probe, or validator
                raised. Every resource acquired here is released first, so a
                partial failure leaves nothing open.
        """
        with self._session_operation():
            self._reopen_transport()

            if not (probe or validate_identity is not None):
                return

            try:
                if probe:
                    self._probe()
                if validate_identity is not None:
                    validate_identity(self.get_identity())
            except BaseException:
                # The connection is not usable, so do not leave it half-open.
                with suppress(Exception):
                    self.close()
                raise

    def _reopen_transport(self) -> None:
        """Acquire the transport resource and start a new connection generation."""
        self.transport.open()
        self._generation += 1
        self._identity = None
        self._health.record_connected()
        self._publish_trace_context()

    def recover_if_faulted(self) -> None:
        """Reopen the transport if a previous failure left it unusable.

        A byte transport moves to a faulted state on any I/O error and
        releases its resource as part of that (see ``Transport``'s contract) —
        that's true across every backend, not an edge case. So resuming a
        retried operation after one requires reopening first; without it,
        every subsequent attempt fails immediately with ``NotConnectedError``
        instead of ever reaching the instrument again.

        Meant to be passed as ``ScpiClient.query(..., before_retry=...)``.
        Unlike :meth:`open`, this never probes or validates identity — it runs
        between retries of a single operation, not at connection setup — and
        does nothing if the transport is already open.

        Raises:
            ScpiDriverError: whatever the transport raised trying to reopen.
        """
        with self._session_operation():
            if self.transport.state is not TransportState.OPEN:
                self._reopen_transport()

    def close(self) -> None:
        """Close the transport and forget everything tied to this connection."""
        with self._session_operation():
            try:
                self.transport.close()
            finally:
                self._identity = None
                self._health.record_disconnected()

    # -- talking to the instrument ----------------------------------------

    def check_communication(self, *, timeout_s: float | None = None) -> bool:
        """Ask the instrument whether it is there, and record what happened.

        This performs real I/O, unlike :attr:`is_connected`.

        Returns:
            Whether the instrument answered. A failure is reported rather than
            raised, since a health check is usually asked as a question; the
            reason is kept on :attr:`health`.
        """
        with self._session_operation():
            try:
                self._probe(timeout_s=timeout_s)
            except ScpiDriverError:
                return False
            return True

    def _publish_trace_context(self) -> None:
        """Tell the tracer which connection generation events now belong to."""
        if self._tracer is not None:
            self._tracer.set_context(
                TraceContext(session_alias=self._alias, session_generation=self._generation)
            )

    def _probe(self, *, timeout_s: float | None = None) -> None:
        """Run the health query, updating health either way, and re-raise on failure."""
        effective = self._communication_timeout_s if timeout_s is None else timeout_s
        try:
            self._client.query(self._health_query, timeout_s=effective)
        except ScpiDriverError as exc:
            self._health.record_failure(exc)
            raise
        self._health.record_success()

    def get_identity(self, *, refresh: bool = False) -> Identity:
        """Return the instrument's identity, querying only when needed.

        The result is cached for the life of one connection and dropped on
        close, so it can never describe a previous connection.

        Args:
            refresh: query again even if a value is cached.
        """
        with self._session_operation():
            if self._identity is None or refresh:
                self._identity = self._ieee488.identify()
                self._health.record_success()
            return self._identity
