"""Deterministic in-memory transport.

:class:`MockTransport` is shipped rather than confined to the test suite: it is
the reference implementation of the :class:`~scpi_driver_core.transport.base.Transport`
contract, and concrete device simulators in other packages build on it.

It never sleeps and never touches the network. An operation that cannot be
satisfied from the buffered data raises immediately instead of waiting, which
is what makes it deterministic; the timeout a caller passes is recorded rather
than observed.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, Literal

from scpi_driver_core.exceptions import (
    ConfigurationError,
    NotConnectedError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)

__all__ = ["DEFAULT_TIMEOUT_S", "MockOperation", "MockTransport"]

DEFAULT_TIMEOUT_S: Final = 5.0

OperationKind = Literal["open", "close", "write", "read", "flush"]


@dataclass(frozen=True)
class MockOperation:
    """One operation performed against a :class:`MockTransport`."""

    kind: OperationKind
    data: bytes = b""
    timeout_s: float = DEFAULT_TIMEOUT_S
    operation_id: str | None = None


@dataclass
class _Injection:
    """A failure queued to fire on the next operation of a given kind."""

    error: Exception
    fault: bool


def _validate_optional_timeout(timeout_s: float | None) -> None:
    """Allow ``None`` (meaning "use the transport default") but nothing unbounded."""
    if timeout_s is None:
        return
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")


class MockTransport:
    """An in-memory :class:`~scpi_driver_core.transport.base.Transport`.

    Data to be read is queued with :meth:`feed`. Each fed chunk is one discrete
    message for :attr:`ReadMode.BACKEND_DEFINED_MESSAGE`, while the stream modes
    see the concatenation of every chunk, mirroring the difference between a
    message-oriented backend such as VISA and a stream such as TCP.

    Args:
        descriptor: identity reported by the transport.
        timeout_s: default bound applied when a caller passes ``timeout_s=None``.
        max_write_chunk: if set, the simulated backend accepts at most this many
            bytes per underlying send, so :meth:`write` has to loop. The data
            still arrives in full; the fragmentation is visible in
            :attr:`write_chunks`.

    Raises:
        ConfigurationError: if the default timeout is not finite and positive,
            or ``max_write_chunk`` is not positive.
    """

    def __init__(
        self,
        *,
        descriptor: TransportDescriptor | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_write_chunk: int | None = None,
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
        if max_write_chunk is not None and max_write_chunk <= 0:
            raise ConfigurationError(f"max_write_chunk must be positive, got {max_write_chunk!r}")

        self._descriptor = descriptor or TransportDescriptor(kind="mock", address="mock")
        self._default_timeout_s = timeout_s
        self._max_write_chunk = max_write_chunk
        self._lock = threading.RLock()
        self._state = TransportState.CREATED
        self._inbound: deque[bytes] = deque()
        self._resource_held = False
        self._fail_open: _Injection | None = None
        self._fail_write: _Injection | None = None
        self._fail_read: _Injection | None = None

        self.transitions: list[TransportState] = []
        """Every state the transport has entered, in order."""

        self.operations: list[MockOperation] = []
        """Every completed operation, in order."""

        self.write_chunks: list[bytes] = []
        """Underlying sends, showing fragmentation when ``max_write_chunk`` is set."""

        self.replay_policies: list[ReplayPolicy] = []
        """The policy each :meth:`transact` was called with, in order."""

        self.open_count = 0
        """How many times a backend resource has been acquired."""

        self.release_count = 0
        """How many times a backend resource has been released."""

        self.on_transact_midpoint: Callable[[], None] | None = None
        """Test hook invoked between a transaction's write and its read.

        Set it to something that yields the GIL to prove that :meth:`transact`
        holds its lock across both halves.
        """

    # -- introspection ----------------------------------------------------

    @property
    def state(self) -> TransportState:
        with self._lock:
            return self._state

    @property
    def is_open(self) -> bool:
        return self.state is TransportState.OPEN

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._descriptor

    @property
    def default_timeout_s(self) -> float:
        return self._default_timeout_s

    @property
    def written(self) -> bytes:
        """Every byte written so far, concatenated."""
        with self._lock:
            return b"".join(op.data for op in self.operations if op.kind == "write")

    @property
    def pending_bytes(self) -> int:
        """How many fed bytes remain unread."""
        with self._lock:
            return sum(len(chunk) for chunk in self._inbound)

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """Hold this transport's lock across several operations.

        A transport composed on top of this one uses it to keep a write and its
        matching read indivisible, the same guarantee :meth:`transact` gives.
        """
        with self._lock:
            yield

    # -- control surface --------------------------------------------------

    def feed(self, data: bytes) -> None:
        """Queue ``data`` as one message for a later read."""
        with self._lock:
            self._inbound.append(data)

    def fail_next_open(self, error: Exception) -> None:
        """Make the next :meth:`open` raise ``error`` and leave the transport faulted."""
        with self._lock:
            self._fail_open = _Injection(error=error, fault=True)

    def fail_next_write(self, error: Exception, *, fault: bool = True) -> None:
        """Make the next :meth:`write` raise ``error``.

        Args:
            fault: whether the failure leaves session validity uncertain. When
                true the transport moves to :attr:`TransportState.FAULTED`.
        """
        with self._lock:
            self._fail_write = _Injection(error=error, fault=fault)

    def fail_next_read(self, error: Exception, *, fault: bool = True) -> None:
        """Make the next :meth:`read` raise ``error``. See :meth:`fail_next_write`."""
        with self._lock:
            self._fail_read = _Injection(error=error, fault=fault)

    def simulate_disconnect(self) -> None:
        """Drop the connection the way a peer vanishing would."""
        with self._lock:
            self._release()
            self._inbound.clear()
            self._set_state(TransportState.FAULTED)

    # -- lifecycle --------------------------------------------------------

    def open(self) -> TransportDescriptor:
        """Acquire the simulated resource.

        Reopening from :attr:`TransportState.FAULTED` releases the failed
        resource first. Opening an already-open transport is a no-op.
        """
        with self._lock:
            if self._state is TransportState.OPEN:
                return self._descriptor
            if self._state is TransportState.FAULTED:
                self._release()

            self._set_state(TransportState.OPENING)
            injection = self._take_injection("open")
            if injection is not None:
                self._set_state(TransportState.FAULTED)
                raise injection.error

            self._resource_held = True
            self.open_count += 1
            self._set_state(TransportState.OPEN)
            self._record("open")
            return self._descriptor

    def close(self) -> None:
        """Release the simulated resource and discard buffered data."""
        with self._lock:
            if self._state in (TransportState.CREATED, TransportState.CLOSED):
                return
            self._set_state(TransportState.CLOSING)
            self._release()
            self._inbound.clear()
            self._set_state(TransportState.CLOSED)
            self._record("close")

    # -- I/O --------------------------------------------------------------

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        """Accept ``data`` verbatim, fragmenting it if ``max_write_chunk`` is set."""
        _validate_optional_timeout(timeout_s)
        with self._lock:
            self._require_open()
            self._fire_injection("write")

            chunk_size = self._max_write_chunk or max(len(data), 1)
            for start in range(0, len(data), chunk_size):
                self.write_chunks.append(data[start : start + chunk_size])

            self._record("write", data, timeout_s, operation_id)
            return WriteResult(bytes_written=len(data))

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes:
        """Satisfy ``request`` from buffered data, or raise immediately."""
        _validate_optional_timeout(timeout_s)
        with self._lock:
            self._require_open()
            self._fire_injection("read")

            data = self._read_buffered(request)
            self._record("read", data, timeout_s, operation_id)
            return data

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes:
        """Write then read while holding the lock across both halves."""
        with self._lock:
            self.replay_policies.append(replay_policy)
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            if self.on_transact_midpoint is not None:
                self.on_transact_midpoint()
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        """Discard buffered data. The mock has no outbound buffer to drop."""
        with self._lock:
            self._require_open()
            if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                self._inbound.clear()
            self._record("flush")

    # -- internals --------------------------------------------------------

    def _set_state(self, state: TransportState) -> None:
        self._state = state
        self.transitions.append(state)

    def _release(self) -> None:
        if self._resource_held:
            self._resource_held = False
            self.release_count += 1

    def _require_open(self) -> None:
        if self._state is not TransportState.OPEN:
            raise NotConnectedError(f"transport is {self._state.name}, not OPEN")

    def _effective_timeout(self, timeout_s: float | None) -> float:
        return self._default_timeout_s if timeout_s is None else timeout_s

    def _record(
        self,
        kind: OperationKind,
        data: bytes = b"",
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> None:
        self.operations.append(
            MockOperation(
                kind=kind,
                data=data,
                timeout_s=self._effective_timeout(timeout_s),
                operation_id=operation_id,
            )
        )

    def _take_injection(self, kind: OperationKind) -> _Injection | None:
        if kind == "open":
            injection, self._fail_open = self._fail_open, None
        elif kind == "write":
            injection, self._fail_write = self._fail_write, None
        else:
            injection, self._fail_read = self._fail_read, None
        return injection

    def _fire_injection(self, kind: OperationKind) -> None:
        injection = self._take_injection(kind)
        if injection is None:
            return
        if injection.fault:
            self._release()
            self._set_state(TransportState.FAULTED)
        raise injection.error

    def _consume(self, count: int) -> bytes:
        taken = bytearray()
        while count > 0 and self._inbound:
            chunk = self._inbound.popleft()
            if len(chunk) > count:
                taken += chunk[:count]
                self._inbound.appendleft(chunk[count:])
                break
            taken += chunk
            count -= len(chunk)
        return bytes(taken)

    def _read_buffered(self, request: ReadRequest) -> bytes:
        if request.mode is ReadMode.BACKEND_DEFINED_MESSAGE:
            if not self._inbound:
                raise TransportTimeoutError("no message available")
            message = self._inbound.popleft()
            if len(message) > request.maximum_size:
                raise TransportError(
                    f"message of {len(message)} bytes exceeds maximum_size {request.maximum_size}"
                )
            return message

        stream = b"".join(self._inbound)

        if request.mode is ReadMode.AVAILABLE:
            return self._consume(min(len(stream), request.maximum_size))

        if request.mode is ReadMode.EXACT_LENGTH:
            length = request.length
            assert length is not None  # guaranteed by ReadRequest validation
            if len(stream) < length:
                raise TransportTimeoutError(f"needed {length} bytes, {len(stream)} available")
            return self._consume(length)

        if request.mode is ReadMode.UP_TO_LENGTH:
            length = request.length
            assert length is not None  # guaranteed by ReadRequest validation
            if not stream:
                raise TransportTimeoutError("no data available")
            return self._consume(min(len(stream), length))

        terminator = request.terminator
        assert terminator is not None  # guaranteed by ReadRequest validation
        index = stream.find(terminator)
        if index < 0:
            if len(stream) >= request.maximum_size:
                raise TransportError(f"no terminator within maximum_size {request.maximum_size}")
            raise TransportTimeoutError("terminator not received")

        end = index + len(terminator)
        if end > request.maximum_size:
            raise TransportError(
                f"message of {end} bytes exceeds maximum_size {request.maximum_size}"
            )
        data = self._consume(end)
        return data if request.include_terminator else data[: -len(terminator)]
