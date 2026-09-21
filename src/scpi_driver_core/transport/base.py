"""The canonical byte-oriented transport contract.

Every backend (VISA, serial, TCP, UDP, mock) implements :class:`Transport`.
The boundary is deliberately ``bytes`` rather than ``str``: waveform captures,
arbitrary-waveform uploads, and setup/file transfers all have to cross it
intact. SCPI text framing belongs above this layer, in the codec and client.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Protocol, runtime_checkable

from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)

__all__ = [
    "SupportsBusTrigger",
    "SupportsDeviceClear",
    "SupportsLocalControl",
    "SupportsSerialPoll",
    "Transport",
]


@runtime_checkable
class SupportsDeviceClear(Protocol):
    """Transport can issue an explicit device clear without closing the session."""

    def device_clear(self) -> None: ...


@runtime_checkable
class SupportsSerialPoll(Protocol):
    """Transport can read the IEEE-488 status byte outside the message queue."""

    def read_status_byte(self, *, timeout_s: float | None = None) -> int: ...


@runtime_checkable
class SupportsBusTrigger(Protocol):
    """Transport can issue its backend's bus-level trigger primitive."""

    def assert_trigger(self) -> None: ...


@runtime_checkable
class SupportsLocalControl(Protocol):
    """Transport can return a remotely controlled instrument to local control."""

    def go_to_local(self) -> None: ...


@runtime_checkable
class Transport(Protocol):
    """A bounded, byte-oriented connection to an instrument.

    Normative read semantics:

    * ``UNTIL_TERMINATOR`` waits for the requested terminator, within
      ``maximum_size``, or times out.
    * ``EXACT_LENGTH`` waits for exactly ``length`` bytes. The *whole call* is
      bounded by ``timeout_s``; partial progress never restarts that deadline.
    * ``UP_TO_LENGTH`` waits for at least one byte, then returns immediately
      with whatever is already available, up to ``length``.
    * ``AVAILABLE`` is the same shape as ``UP_TO_LENGTH`` but is bounded only by
      ``maximum_size``. Empty input is a timeout, not a successful empty read.
    * ``BACKEND_DEFINED_MESSAGE`` returns one backend message (for example a
      VISA END-delimited message), or is unsupported on raw streams.

    The safe default after a read/write timeout is ``FAULTED``: once a request
    may have reached an instrument, a late response must never be allowed to
    become the next query's answer. A backend offering a cheaper recovery
    mechanism may expose it as an explicit capability, but must document any
    non-faulting profile separately.

    Other lifecycle rules enforced by the contract suite:

    * :meth:`close` is idempotent and always releases the backend resource.
    * I/O while not ``OPEN`` fails before anything is transmitted.
    * any escaping interruption during an exchange invalidates the transport;
    * reopening a faulted transport acquires a fresh backend resource;
    * all operations are finite-time and serialized;
    * multi-step protocol readers may use :meth:`operation_lock` and
      :meth:`invalidate` to preserve framing integrity.
    """

    @property
    def state(self) -> TransportState:
        """Current resource state. Introspection must not wait for in-flight I/O."""
        ...

    @property
    def is_open(self) -> bool:
        """Whether the backend resource is held; no device I/O is performed."""
        ...

    @property
    def descriptor(self) -> TransportDescriptor:
        """Identity of this transport, available before and after opening."""
        ...

    def open(self) -> TransportDescriptor: ...

    def close(self) -> None: ...

    def invalidate(self) -> None:
        """Release an open resource and move to ``FAULTED`` after desynchronization."""
        ...

    def operation_lock(self) -> AbstractContextManager[None]:
        """Serialize a multi-call operation at the transport level."""
        ...

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult: ...

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes: ...

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes: ...

    def flush(self, direction: FlushDirection) -> None:
        """Discard locally buffered data. It must not implicitly clear the device."""
        ...
