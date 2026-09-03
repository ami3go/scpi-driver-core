"""The high-level SCPI client.

Every piece of SCPI traffic goes through one execution choke point,
:meth:`ScpiClient._execute`, so that locking, operation-identifier assignment,
and timeout resolution are applied uniformly instead of being reimplemented per
call site. Tracing and error-queue policy hook into the same place in later
phases.

The client deliberately does not open or close the transport. Owning the
connection lifecycle belongs to the session layer; the client's single
responsibility is protocol.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import TypeVar

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.scpi.codec import ScpiTextCodec
from scpi_driver_core.scpi.parsers import (
    parse_bool,
    parse_csv,
    parse_float,
    parse_int,
    parse_optional_unit_float,
)
from scpi_driver_core.transport.base import Transport
from scpi_driver_core.transport.models import (
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    TransportState,
)

__all__ = ["ScpiClient"]

_T = TypeVar("_T")


def _counting_operation_ids() -> Callable[[], str]:
    """Return a factory yielding ``op-1``, ``op-2``, ... for one client."""
    counter = 0
    lock = threading.Lock()

    def next_id() -> str:
        nonlocal counter
        with lock:
            counter += 1
            return f"op-{counter}"

    return next_id


class ScpiClient:
    """Sends SCPI commands and parses responses over a byte transport.

    Args:
        transport: the opened, or yet to be opened, byte transport.
        codec: text framing. Defaults to ASCII with ``\\n`` terminators.
        response_request: how a query's reply is read. Defaults to reading up
            to the codec's response terminator, or to one backend-framed
            message when the codec has no response terminator, as with VISA.
        timeout_s: default bound for this client's operations. ``None`` defers
            to the transport's own default.
        operation_id_factory: supplies correlation identifiers. The default
            numbers operations from one within this client.

    Raises:
        ConfigurationError: if ``timeout_s`` is not finite and positive.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        codec: ScpiTextCodec | None = None,
        response_request: ReadRequest | None = None,
        timeout_s: float | None = None,
        operation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        if timeout_s is not None and not (timeout_s > 0 and timeout_s != float("inf")):
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")

        self._transport = transport
        self._codec = codec if codec is not None else ScpiTextCodec()
        self._timeout_s = timeout_s
        self._next_operation_id = (
            operation_id_factory if operation_id_factory is not None else _counting_operation_ids()
        )
        self._response_request = (
            response_request if response_request is not None else self._default_response_request()
        )
        self._lock = threading.RLock()

    def _default_response_request(self) -> ReadRequest:
        terminator = self._codec.response_terminator
        if terminator:
            return ReadRequest(
                mode=ReadMode.UNTIL_TERMINATOR,
                terminator=terminator,
                include_terminator=True,
                maximum_size=self._codec.maximum_response_size,
            )
        return ReadRequest(
            mode=ReadMode.BACKEND_DEFINED_MESSAGE,
            maximum_size=self._codec.maximum_response_size,
        )

    # -- introspection ----------------------------------------------------

    @property
    def transport(self) -> Transport:
        return self._transport

    @property
    def codec(self) -> ScpiTextCodec:
        return self._codec

    @property
    def timeout_s(self) -> float | None:
        return self._timeout_s

    @property
    def response_request(self) -> ReadRequest:
        """The read used for a query reply."""
        return self._response_request

    @property
    def is_open(self) -> bool:
        """Whether the underlying transport holds its resource."""
        return self._transport.state is TransportState.OPEN

    # -- execution --------------------------------------------------------

    @contextmanager
    def operation_lock(self) -> Iterator[None]:
        """Hold the client's lock across several operations.

        Use this where a sequence has to be indivisible, such as a write
        followed by the error-queue check that belongs to it, so that a
        concurrent caller cannot consume the result in between.
        """
        with self._lock:
            yield

    def _execute(self, action: Callable[[str, float | None], _T], *, timeout_s: float | None) -> _T:
        """The single choke point every SCPI operation passes through."""
        if timeout_s is not None and not (timeout_s > 0 and timeout_s != float("inf")):
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
        effective = self._timeout_s if timeout_s is None else timeout_s
        with self._lock:
            return action(self._next_operation_id(), effective)

    # -- byte operations --------------------------------------------------

    def write_bytes(self, data: bytes, *, timeout_s: float | None = None) -> None:
        """Send raw bytes with no framing added."""

        def action(operation_id: str, effective: float | None) -> None:
            self._transport.write(data, timeout_s=effective, operation_id=operation_id)

        self._execute(action, timeout_s=timeout_s)

    def read_bytes(self, request: ReadRequest, *, timeout_s: float | None = None) -> bytes:
        """Read raw bytes according to ``request``."""

        def action(operation_id: str, effective: float | None) -> bytes:
            return self._transport.read(request, timeout_s=effective, operation_id=operation_id)

        return self._execute(action, timeout_s=timeout_s)

    def transact_bytes(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
    ) -> bytes:
        """Write raw bytes and read the reply as one indivisible operation."""

        def action(operation_id: str, effective: float | None) -> bytes:
            return self._transport.transact(
                outbound,
                response,
                timeout_s=effective,
                replay_policy=replay_policy,
                operation_id=operation_id,
            )

        return self._execute(action, timeout_s=timeout_s)

    # -- text operations --------------------------------------------------

    def write(self, command: str, *, timeout_s: float | None = None) -> None:
        """Send a SCPI command, terminated by the codec."""
        self.write_bytes(self._codec.encode_command(command), timeout_s=timeout_s)

    def query(
        self,
        command: str,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
    ) -> str:
        """Send a query and return its decoded reply.

        Args:
            replay_policy: left at ``NEVER`` unless the caller knows this
                particular query is free of side effects.
        """
        raw = self.transact_bytes(
            self._codec.encode_command(command),
            self._response_request,
            timeout_s=timeout_s,
            replay_policy=replay_policy,
        )
        return self._codec.decode_response(raw)

    # -- typed queries ----------------------------------------------------

    def query_float(
        self,
        command: str,
        *,
        allow_non_finite: bool = False,
        timeout_s: float | None = None,
    ) -> float:
        """Query and parse a float."""
        return parse_float(
            self.query(command, timeout_s=timeout_s), allow_non_finite=allow_non_finite
        )

    def query_int(self, command: str, *, timeout_s: float | None = None) -> int:
        """Query and parse an integer."""
        return parse_int(self.query(command, timeout_s=timeout_s))

    def query_bool(self, command: str, *, timeout_s: float | None = None) -> bool:
        """Query and parse a SCPI boolean."""
        return parse_bool(self.query(command, timeout_s=timeout_s))

    def query_csv(self, command: str, *, timeout_s: float | None = None) -> list[str]:
        """Query and split a comma-separated reply."""
        return parse_csv(self.query(command, timeout_s=timeout_s))

    def query_optional_unit_float(
        self,
        command: str,
        *,
        expected_unit: str | None = None,
        allow_non_finite: bool = False,
        timeout_s: float | None = None,
    ) -> float:
        """Query a number that the instrument may or may not suffix with a unit."""
        return parse_optional_unit_float(
            self.query(command, timeout_s=timeout_s),
            expected_unit=expected_unit,
            allow_non_finite=allow_non_finite,
        )
