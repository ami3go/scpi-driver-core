"""The high-level SCPI client.

Every protocol operation passes through one execution choke point so locking,
operation identifiers, pacing, outcome reporting and timeout resolution remain
consistent across text, raw-byte and binary-block traffic.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from typing import TypeVar

from scpi_driver_core.exceptions import ConfigurationError, ScpiDriverError
from scpi_driver_core.execution.retry import RetryAttempt, RetryPolicy, run_with_retry
from scpi_driver_core.scpi.binary_block import (
    DEFAULT_MAXIMUM_BLOCK_SIZE,
    encode_definite_length_block,
    read_definite_length_block,
)
from scpi_driver_core.scpi.codec import ScpiTextCodec
from scpi_driver_core.scpi.errors import ScpiErrorQueue, ScpiExecutionPolicy
from scpi_driver_core.scpi.parsers import (
    parse_bool,
    parse_csv,
    parse_csv_floats,
    parse_float,
    parse_int,
    parse_optional_unit_float,
)
from scpi_driver_core.transport.base import Transport
from scpi_driver_core.transport.models import ReadMode, ReadRequest, ReplayPolicy, TransportState

__all__ = ["ScpiClient"]

_T = TypeVar("_T")
OutcomeListener = Callable[[ScpiDriverError | None], None]


def _counting_operation_ids() -> Callable[[], str]:
    counter = 0
    lock = threading.Lock()

    def next_id() -> str:
        nonlocal counter
        with lock:
            counter += 1
            return f"op-{counter}"

    return next_id


class ScpiClient:
    """Send SCPI commands and parse responses over one byte transport."""

    def __init__(
        self,
        transport: Transport,
        *,
        codec: ScpiTextCodec | None = None,
        response_request: ReadRequest | None = None,
        timeout_s: float | None = None,
        operation_id_factory: Callable[[], str] | None = None,
        retry_observer: Callable[[RetryAttempt], None] | None = None,
        minimum_interval_s: float | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        if timeout_s is not None and not (timeout_s > 0 and timeout_s != float("inf")):
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
        if minimum_interval_s is not None and not (
            minimum_interval_s > 0 and minimum_interval_s != float("inf")
        ):
            raise ConfigurationError(
                f"minimum_interval_s must be finite and positive, got {minimum_interval_s!r}"
            )
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
        self._retry_observer = retry_observer
        self._error_queue: ScpiErrorQueue | None = None
        self._execution_policy = ScpiExecutionPolicy()
        self._checking_errors = False
        self._minimum_interval_s = minimum_interval_s
        self._sleep = sleep
        self._now = now
        self._last_operation_at: float | None = None
        self._outcome_listeners: list[OutcomeListener] = []

    def _default_response_request(self) -> ReadRequest:
        terminator = self._codec.response_terminator
        message_based = bool(getattr(self._transport, "message_based", False))
        if terminator and not message_based:
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
        return self._response_request

    @property
    def is_open(self) -> bool:
        return self._transport.state is TransportState.OPEN

    def add_outcome_listener(self, listener: OutcomeListener) -> None:
        """Observe completed transport/protocol operations for health tracking."""
        with self._lock:
            if listener not in self._outcome_listeners:
                self._outcome_listeners.append(listener)

    def remove_outcome_listener(self, listener: OutcomeListener) -> None:
        with self._lock:
            if listener in self._outcome_listeners:
                self._outcome_listeners.remove(listener)

    def _notify_outcome(self, error: ScpiDriverError | None) -> None:
        for listener in tuple(self._outcome_listeners):
            with suppress(Exception):
                listener(error)

    def enable_error_checking(
        self, error_queue: ScpiErrorQueue, policy: ScpiExecutionPolicy
    ) -> None:
        with self._lock:
            self._error_queue = error_queue
            self._execution_policy = policy

    def disable_error_checking(self) -> None:
        with self._lock:
            self._error_queue = None
            self._execution_policy = ScpiExecutionPolicy()

    @property
    def execution_policy(self) -> ScpiExecutionPolicy:
        return self._execution_policy

    @property
    def error_queue(self) -> ScpiErrorQueue | None:
        return self._error_queue

    def _check_errors(self, *, after_query: bool) -> None:
        queue = self._error_queue
        if queue is None or self._checking_errors:
            return
        policy = self._execution_policy
        wanted = (
            policy.check_error_queue_after_query
            if after_query
            else policy.check_error_queue_after_write
        )
        if not wanted:
            return
        self._checking_errors = True
        try:
            queue.raise_if_errors()
        finally:
            self._checking_errors = False

    def operation_lock(self) -> AbstractContextManager[None]:
        """Hold the client's serialization lock across several operations."""
        return self._operation_lock()

    @contextmanager
    def _operation_lock(self) -> Iterator[None]:
        with self._lock:
            yield

    def _execute(self, action: Callable[[str, float | None], _T], *, timeout_s: float | None) -> _T:
        if timeout_s is not None and not (timeout_s > 0 and timeout_s != float("inf")):
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
        effective = self._timeout_s if timeout_s is None else timeout_s
        with self._lock:
            self._wait_for_pacing()
            try:
                result = action(self._next_operation_id(), effective)
            except ScpiDriverError as exc:
                self._notify_outcome(exc)
                raise
            finally:
                if self._minimum_interval_s is not None:
                    self._last_operation_at = self._now()
            self._notify_outcome(None)
            return result

    def _wait_for_pacing(self) -> None:
        if self._minimum_interval_s is None or self._last_operation_at is None:
            return
        remaining = self._minimum_interval_s - (self._now() - self._last_operation_at)
        if remaining > 0:
            self._sleep(remaining)

    def write_bytes(self, data: bytes, *, timeout_s: float | None = None) -> None:
        def action(operation_id: str, effective: float | None) -> None:
            self._transport.write(data, timeout_s=effective, operation_id=operation_id)

        self._execute(action, timeout_s=timeout_s)

    def read_bytes(self, request: ReadRequest, *, timeout_s: float | None = None) -> bytes:
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
        def action(operation_id: str, effective: float | None) -> bytes:
            return self._transport.transact(
                outbound,
                response,
                timeout_s=effective,
                replay_policy=replay_policy,
                operation_id=operation_id,
            )

        return self._execute(action, timeout_s=timeout_s)

    def write(self, command: str, *, timeout_s: float | None = None) -> None:
        """Send one SCPI command. Writes are never retried automatically."""
        with self._lock:
            self.write_bytes(self._codec.encode_command(command), timeout_s=timeout_s)
            self._check_errors(after_query=False)

    def query(
        self,
        command: str,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        retry_policy: RetryPolicy | None = None,
        before_retry: Callable[[], None] | None = None,
    ) -> str:
        if (
            retry_policy is not None
            and retry_policy.retries
            and replay_policy is not ReplayPolicy.SAFE
        ):
            raise ConfigurationError(
                "retrying a query requires replay_policy=ReplayPolicy.SAFE, "
                "which asserts that resending it has no side effect"
            )
        if before_retry is not None and retry_policy is None:
            raise ConfigurationError("before_retry has no effect without a retry_policy")
        outbound = self._codec.encode_command(command)

        def attempt() -> str:
            raw = self.transact_bytes(
                outbound,
                self._response_request,
                timeout_s=timeout_s,
                replay_policy=replay_policy,
            )
            return self._codec.decode_response(raw)

        # Intentionally retained across backoff/recovery. Releasing this lock
        # would let another command consume a late response or error-queue entry
        # belonging to the operation being recovered.
        with self._lock:
            response = (
                attempt()
                if retry_policy is None
                else run_with_retry(
                    attempt,
                    policy=retry_policy,
                    before_retry=before_retry,
                    on_attempt=self._retry_observer,
                )
            )
            self._check_errors(after_query=True)
            return response

    def query_float(
        self,
        command: str,
        *,
        allow_non_finite: bool = False,
        scpi_special_values: bool = True,
        timeout_s: float | None = None,
    ) -> float:
        return parse_float(
            self.query(command, timeout_s=timeout_s),
            allow_non_finite=allow_non_finite,
            scpi_special_values=scpi_special_values,
        )

    def query_int(self, command: str, *, timeout_s: float | None = None) -> int:
        return parse_int(self.query(command, timeout_s=timeout_s))

    def query_bool(self, command: str, *, timeout_s: float | None = None) -> bool:
        return parse_bool(self.query(command, timeout_s=timeout_s))

    def query_csv(self, command: str, *, timeout_s: float | None = None) -> list[str]:
        return parse_csv(self.query(command, timeout_s=timeout_s))

    def query_csv_floats(
        self,
        command: str,
        *,
        allow_non_finite: bool = False,
        scpi_special_values: bool = True,
        timeout_s: float | None = None,
    ) -> list[float]:
        return parse_csv_floats(
            self.query(command, timeout_s=timeout_s),
            allow_non_finite=allow_non_finite,
            scpi_special_values=scpi_special_values,
        )

    def query_binary_block(
        self,
        command: str,
        *,
        timeout_s: float | None = None,
        maximum_size: int | None = None,
        consume_terminator: bool = True,
    ) -> bytes:
        """Query one definite-length block atomically and invalidate on framing failure."""
        limit = DEFAULT_MAXIMUM_BLOCK_SIZE if maximum_size is None else maximum_size
        terminator = self._codec.response_terminator if consume_terminator else None
        outbound = self._codec.encode_command(command)

        def action(operation_id: str, effective: float | None) -> bytes:
            with self._transport.operation_lock():
                self._transport.write(outbound, timeout_s=effective, operation_id=operation_id)
                try:
                    return read_definite_length_block(
                        self._transport,
                        timeout_s=effective,
                        maximum_size=limit,
                        terminator=terminator,
                        operation_id=operation_id,
                    )
                except BaseException:
                    with suppress(Exception):
                        self._transport.invalidate()
                    raise

        with self._lock:
            payload = self._execute(action, timeout_s=timeout_s)
            self._check_errors(after_query=True)
            return payload

    def write_binary_block(
        self,
        command_prefix: str,
        payload: bytes,
        *,
        timeout_s: float | None = None,
    ) -> None:
        data = self._codec.encode_block_command(
            command_prefix, encode_definite_length_block(payload)
        )
        with self._lock:
            self.write_bytes(data, timeout_s=timeout_s)
            self._check_errors(after_query=False)

    def query_optional_unit_float(
        self,
        command: str,
        *,
        expected_unit: str | None = None,
        allow_non_finite: bool = False,
        scpi_special_values: bool = True,
        timeout_s: float | None = None,
    ) -> float:
        return parse_optional_unit_float(
            self.query(command, timeout_s=timeout_s),
            expected_unit=expected_unit,
            allow_non_finite=allow_non_finite,
            scpi_special_values=scpi_special_values,
        )
