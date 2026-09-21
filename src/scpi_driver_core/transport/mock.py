"""Deterministic in-memory transport used as the transport-contract simulator."""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal, NoReturn

from scpi_driver_core.exceptions import ConfigurationError, TransportError, TransportTimeoutError
from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)
from scpi_driver_core.transport.state import TransportStateMachine

__all__ = ["DEFAULT_TIMEOUT_S", "MockOperation", "MockTransport"]

DEFAULT_TIMEOUT_S: Final = 5.0
OperationKind = Literal["open", "close", "write", "read", "flush"]


@dataclass(frozen=True)
class MockOperation:
    kind: OperationKind
    data: bytes = b""
    timeout_s: float = DEFAULT_TIMEOUT_S
    operation_id: str | None = None


@dataclass
class _Injection:
    error: Exception
    fault: bool


def _validate_optional_timeout(timeout_s: float | None) -> None:
    if timeout_s is None:
        return
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")


class MockTransport(TransportStateMachine):
    """In-memory transport following the same default timeout state as hardware.

    ``fault_on_timeout=True`` is the contract-faithful default. Tests that need
    to model a deliberately non-faulting legacy/datagram endpoint can opt out
    explicitly; doing so is a simulation profile, not the reference behavior.
    """

    def __init__(
        self,
        *,
        descriptor: TransportDescriptor | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        max_write_chunk: int | None = None,
        fault_on_timeout: bool = True,
        available_when_empty: Literal["timeout", "empty"] = "timeout",
    ) -> None:
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ConfigurationError(f"timeout_s must be finite and positive, got {timeout_s!r}")
        if max_write_chunk is not None and max_write_chunk <= 0:
            raise ConfigurationError(f"max_write_chunk must be positive, got {max_write_chunk!r}")
        if available_when_empty not in ("timeout", "empty"):
            raise ConfigurationError("available_when_empty must be 'timeout' or 'empty'")
        super().__init__(descriptor or TransportDescriptor(kind="mock", address="mock"))
        self._default_timeout_s = timeout_s
        self._max_write_chunk = max_write_chunk
        self._fault_on_timeout = fault_on_timeout
        self._available_when_empty = available_when_empty
        self._inbound: deque[bytes] = deque()
        self._resource_held = False
        self._fail_open: _Injection | None = None
        self._fail_write: _Injection | None = None
        self._fail_read: _Injection | None = None
        self.transitions: list[TransportState] = []
        self.operations: list[MockOperation] = []
        self.write_chunks: list[bytes] = []
        self.replay_policies: list[ReplayPolicy] = []
        self.open_count = 0
        self.release_count = 0
        self.on_transact_midpoint: Callable[[], None] | None = None

    @property
    def default_timeout_s(self) -> float:
        return self._default_timeout_s

    @property
    def written(self) -> bytes:
        with self._lock:
            return b"".join(op.data for op in self.operations if op.kind == "write")

    @property
    def pending_bytes(self) -> int:
        with self._lock:
            return sum(len(chunk) for chunk in self._inbound)

    def feed(self, data: bytes) -> None:
        with self._lock:
            self._inbound.append(data)

    def fail_next_open(self, error: Exception) -> None:
        with self._lock:
            self._fail_open = _Injection(error=error, fault=True)

    def fail_next_write(self, error: Exception, *, fault: bool = True) -> None:
        with self._lock:
            self._fail_write = _Injection(error=error, fault=fault)

    def fail_next_read(self, error: Exception, *, fault: bool = True) -> None:
        with self._lock:
            self._fail_read = _Injection(error=error, fault=fault)

    def simulate_disconnect(self) -> None:
        with self._lock:
            self._release_resource()
            self._inbound.clear()
            self._set_state(TransportState.FAULTED)

    def open(self) -> TransportDescriptor:
        with self._lock:
            if self.state is TransportState.OPEN:
                return self._descriptor
            if self.state is TransportState.FAULTED:
                self._release_resource()
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
        with self._lock:
            was_live = self.state not in (TransportState.CREATED, TransportState.CLOSED)
            super().close()
            if was_live:
                self._record("close")

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
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
        with self._lock:
            self.replay_policies.append(replay_policy)
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            if self.on_transact_midpoint is not None:
                self.on_transact_midpoint()
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        with self._lock:
            self._require_open()
            if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                self._inbound.clear()
            self._record("flush")

    def _set_state(self, state: TransportState) -> None:
        super()._set_state(state)
        self.transitions.append(state)

    def _on_closed(self) -> None:
        self._inbound.clear()

    def _release_resource(self) -> None:
        if self._resource_held:
            self._resource_held = False
            self.release_count += 1

    def _require_open(self) -> None:
        self._require_state_open()

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
            self._fault()
        raise injection.error

    def _timeout(self, message: str) -> NoReturn:
        if self._fault_on_timeout:
            self._fault()
        raise TransportTimeoutError(message)

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
                self._timeout("no message available")
            message = self._inbound.popleft()
            if len(message) > request.maximum_size:
                raise TransportError(
                    f"message of {len(message)} bytes exceeds maximum_size {request.maximum_size}"
                )
            return message

        stream = b"".join(self._inbound)
        if request.mode is ReadMode.AVAILABLE:
            if not stream:
                if self._available_when_empty == "empty":
                    return b""
                self._timeout("no data available")
            return self._consume(min(len(stream), request.maximum_size))

        if request.mode is ReadMode.EXACT_LENGTH:
            assert request.length is not None
            if len(stream) < request.length:
                self._timeout(f"needed {request.length} bytes, {len(stream)} available")
            return self._consume(request.length)

        if request.mode is ReadMode.UP_TO_LENGTH:
            assert request.length is not None
            if not stream:
                self._timeout("no data available")
            return self._consume(min(len(stream), request.length))

        terminator = request.terminator
        assert terminator is not None
        index = stream.find(terminator)
        if index < 0:
            if len(stream) >= request.maximum_size:
                raise TransportError(f"no terminator within maximum_size {request.maximum_size}")
            self._timeout("terminator not received")
        end = index + len(terminator)
        if end > request.maximum_size:
            raise TransportError(
                f"message of {end} bytes exceeds maximum_size {request.maximum_size}"
            )
        data = self._consume(end)
        return data if request.include_terminator else data[: -len(terminator)]
