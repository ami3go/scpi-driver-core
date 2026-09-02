"""The canonical byte-oriented transport contract.

Every backend (VISA, serial, TCP, UDP, mock) implements :class:`Transport`.
The boundary is deliberately ``bytes`` rather than ``str``: waveform captures,
arbitrary-waveform uploads, and setup/file transfers all have to cross it
intact. SCPI text framing belongs above this layer, in the codec and client.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)

__all__ = ["Transport"]


@runtime_checkable
class Transport(Protocol):
    """A bounded, byte-oriented connection to an instrument.

    Implementations must satisfy the following behavioral contract, which the
    reusable suite in ``tests/transport_contract`` enforces against every
    backend:

    - :meth:`close` is idempotent and always releases the backend resource.
    - I/O attempted while the transport is not :attr:`TransportState.OPEN`
      fails with :class:`~scpi_driver_core.exceptions.NotConnectedError`
      *before* anything is transmitted.
    - An I/O failure that leaves session validity uncertain moves the
      transport to :attr:`TransportState.FAULTED`.
    - Reopening from :attr:`TransportState.FAULTED` releases the failed
      backend resource before acquiring a new one.
    - No operation blocks forever; every one is bounded by a finite timeout.
    - Individual operations are serialized, so concurrent callers cannot
      interleave at the byte level.
    """

    @property
    def state(self) -> TransportState:
        """Current resource state. Says nothing about communication health."""
        ...

    @property
    def is_open(self) -> bool:
        """Whether the backend resource is held.

        This never performs device I/O. A transport can be open while the
        instrument is unresponsive; communication health is tracked separately
        by the session layer.
        """
        ...

    @property
    def descriptor(self) -> TransportDescriptor:
        """Identity of this transport, available before and after opening."""
        ...

    def open(self) -> TransportDescriptor:
        """Acquire the backend resource.

        Returns:
            The descriptor of the opened transport.

        Raises:
            TransportError: if the resource cannot be acquired.
        """
        ...

    def close(self) -> None:
        """Release the backend resource. Safe to call repeatedly."""
        ...

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        """Send ``data`` in full, without adding or removing any byte.

        Args:
            data: exact bytes to transmit. No terminator is appended.
            timeout_s: bound for this call; ``None`` uses the transport default.
            operation_id: correlation identifier carried into trace records.

        Raises:
            NotConnectedError: if the transport is not open.
            TransportTimeoutError: if the write does not complete in time.
        """
        ...

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes:
        """Read according to ``request``, which is always explicitly bounded.

        Raises:
            NotConnectedError: if the transport is not open.
            TransportTimeoutError: if the request is not satisfied in time.
            TransportError: if the response exceeds ``request.maximum_size``.
        """
        ...

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes:
        """Write then read as one indivisible operation.

        The write and its matching read are serialized together, so a
        concurrent caller cannot consume this transaction's response.

        Args:
            replay_policy: whether the backend may retransmit internally.
                ``NEVER`` forbids it. ``SAFE`` permits it only for messages the
                caller has classified as idempotent, and is honored by backends
                where retransmission is meaningful, such as UDP.
        """
        ...

    def flush(self, direction: FlushDirection) -> None:
        """Discard buffered data in ``direction``.

        Raises:
            NotConnectedError: if the transport is not open.
        """
        ...
