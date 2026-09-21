"""A scripted SCPI instrument for hardware-free driver tests."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from types import TracebackType
from typing import Union

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.models import ScpiError
from scpi_driver_core.scpi.binary_block import encode_definite_length_block
from scpi_driver_core.scpi.codec import ScpiTextCodec
from scpi_driver_core.scpi.parsers import quote_scpi_string
from scpi_driver_core.transport.mock import MockTransport
from scpi_driver_core.transport.models import (
    FlushDirection,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)

__all__ = [
    "DEFAULT_ERROR_QUERY",
    "NO_ERROR",
    "UNDEFINED_HEADER",
    "Handler",
    "ScriptedReply",
    "ScriptedScpiTransport",
]

DEFAULT_ERROR_QUERY = "SYST:ERR?"
NO_ERROR = ScpiError(code=0, message="No error", raw='0,"No error"')
UNDEFINED_HEADER = ScpiError(code=-113, message="Undefined header", raw='-113,"Undefined header"')
HandlerResult = Union[str, bytes, "ScriptedReply", None]
Handler = Callable[[str], HandlerResult]


@dataclass(frozen=True)
class ScriptedReply:
    data: bytes = b""
    delay_s: float = 0.0
    raises: Exception | None = None
    disconnect: bool = False

    def __post_init__(self) -> None:
        if self.delay_s < 0:
            raise ConfigurationError("ScriptedReply.delay_s must be non-negative")


@dataclass
class _Rule:
    matcher: Callable[[str], bool]
    handler: Handler
    description: str


@dataclass
class _ExactRule:
    handler: Handler
    description: str = ""


@dataclass
class _State:
    history: list[str] = field(default_factory=list)
    errors: list[ScpiError] = field(default_factory=list)


@dataclass
class _PendingReply:
    remaining_delay_s: float
    reply: ScriptedReply


class ScriptedScpiTransport:
    """A serialized SCPI command-level simulator.

    Compound program messages are split on terminators and on semicolons outside
    quoted strings. Delayed replies are delivered from :meth:`read`, so a delay
    longer than the requested timeout really produces a transport timeout.
    """

    def __init__(
        self,
        *,
        codec: ScpiTextCodec | None = None,
        descriptor: TransportDescriptor | None = None,
        error_query: str = DEFAULT_ERROR_QUERY,
        unknown_command_error: ScpiError | None = UNDEFINED_HEADER,
        timeout_s: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        fault_on_timeout: bool = True,
    ) -> None:
        self._codec = codec if codec is not None else ScpiTextCodec()
        if not self._codec.command_terminator:
            raise ConfigurationError(
                "a scripted instrument needs a command terminator to delimit commands"
            )
        self._inner = MockTransport(
            descriptor=descriptor
            if descriptor is not None
            else TransportDescriptor(kind="scripted", address="scripted://instrument"),
            timeout_s=timeout_s,
            fault_on_timeout=fault_on_timeout,
        )
        self._error_query = error_query
        self._unknown_command_error = unknown_command_error
        self._sleep = sleep
        self._exact: dict[str, _ExactRule] = {}
        self._rules: list[_Rule] = []
        self._state = _State()
        self._pending: list[_PendingReply] = []

    def on(self, command: str, reply: HandlerResult | Handler = None) -> ScriptedScpiTransport:
        self._exact[self._key(command)] = _ExactRule(
            handler=_as_handler(reply), description=command
        )
        return self

    def on_regex(
        self, pattern: str | re.Pattern[str], reply: HandlerResult | Handler = None
    ) -> ScriptedScpiTransport:
        compiled = re.compile(pattern, re.IGNORECASE) if isinstance(pattern, str) else pattern
        self._rules.append(
            _Rule(
                matcher=lambda command: compiled.search(command) is not None,
                handler=_as_handler(reply),
                description=compiled.pattern,
            )
        )
        return self

    def on_predicate(
        self, predicate: Callable[[str], bool], reply: HandlerResult | Handler = None
    ) -> ScriptedScpiTransport:
        self._rules.append(
            _Rule(matcher=predicate, handler=_as_handler(reply), description="predicate")
        )
        return self

    def reply_block(self, command: str, payload: bytes) -> ScriptedScpiTransport:
        return self.on(command, self.block(payload))

    def block(self, payload: bytes) -> bytes:
        return encode_definite_length_block(payload) + (self._codec.response_terminator or b"")

    def push_error(self, error: ScpiError) -> None:
        with self._inner.operation_lock():
            self._state.errors.append(error)

    @property
    def pending_errors(self) -> list[ScpiError]:
        with self._inner.operation_lock():
            return list(self._state.errors)

    @property
    def history(self) -> list[str]:
        with self._inner.operation_lock():
            return list(self._state.history)

    def clear_history(self) -> None:
        with self._inner.operation_lock():
            self._state.history.clear()

    @property
    def inner(self) -> MockTransport:
        return self._inner

    @property
    def state(self) -> TransportState:
        return self._inner.state

    @property
    def is_open(self) -> bool:
        return self._inner.is_open

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._inner.descriptor

    def operation_lock(self) -> AbstractContextManager[None]:
        return self._inner.operation_lock()

    def invalidate(self) -> None:
        self._inner.invalidate()
        with self._inner.operation_lock():
            self._pending.clear()

    def open(self) -> TransportDescriptor:
        descriptor = self._inner.open()
        with self._inner.operation_lock():
            self._pending.clear()
        return descriptor

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            with self._inner.operation_lock():
                self._pending.clear()

    def __enter__(self) -> ScriptedScpiTransport:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        with self._inner.operation_lock():
            result = self._inner.write(data, timeout_s=timeout_s, operation_id=operation_id)
            for command in self._split_program_message(data):
                self._state.history.append(command)
                self._serve(command)
            return result

    def read(
        self,
        request: ReadRequest,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> bytes:
        with self._inner.operation_lock():
            self._deliver_pending(timeout_s)
            try:
                return self._inner.read(request, timeout_s=timeout_s, operation_id=operation_id)
            except BaseException:
                if self._inner.state is TransportState.FAULTED:
                    self._pending.clear()
                raise

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes:
        del replay_policy
        with self._inner.operation_lock():
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        with self._inner.operation_lock():
            if direction in (FlushDirection.INPUT, FlushDirection.BOTH):
                self._pending.clear()
            self._inner.flush(direction)

    def _split_program_message(self, data: bytes) -> list[str]:
        try:
            text = data.decode(self._codec.encoding, errors="strict")
        except UnicodeDecodeError:
            text = data.decode(self._codec.encoding, errors="replace")
        terminator = self._codec.command_terminator.decode(self._codec.encoding)
        physical = text.split(terminator)
        commands: list[str] = []
        for line in physical:
            if not line.strip():
                continue
            commands.extend(self._split_semicolons(line))
        return self._inherit_header_paths(commands)

    @staticmethod
    def _split_semicolons(text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        quoted = False
        index = 0
        while index < len(text):
            char = text[index]
            if char == '"':
                if quoted and index + 1 < len(text) and text[index + 1] == '"':
                    index += 2
                    continue
                quoted = not quoted
            elif char == ";" and not quoted:
                parts.append(text[start:index].strip())
                start = index + 1
            index += 1
        parts.append(text[start:].strip())
        return [part for part in parts if part]

    @staticmethod
    def _inherit_header_paths(parts: list[str]) -> list[str]:
        result: list[str] = []
        parent = ""
        for part in parts:
            stripped = part.strip()
            if stripped.startswith(":"):
                command = stripped[1:]
            elif stripped.startswith("*") or not parent:
                command = stripped
            else:
                command = f"{parent}:{stripped}"
            result.append(command)
            header = command.split(maxsplit=1)[0]
            header = header[:-1] if header.endswith("?") else header
            if ":" in header and not header.startswith("*"):
                parent = header.rsplit(":", 1)[0]
            else:
                parent = ""
        return result

    def _key(self, command: str) -> str:
        return command.strip().casefold()

    def _serve(self, command: str) -> None:
        reply = self._resolve(command)
        if reply is None:
            return
        if reply.delay_s > 0:
            self._pending.append(_PendingReply(reply.delay_s, reply))
        else:
            self._deliver(reply)

    def _deliver_pending(self, timeout_s: float | None) -> None:
        if not self._pending:
            return
        pending = self._pending[0]
        timeout = self._inner.default_timeout_s if timeout_s is None else timeout_s
        wait = pending.remaining_delay_s
        if wait > timeout:
            self._sleep(timeout)
            pending.remaining_delay_s -= timeout
            return
        if wait > 0:
            self._sleep(wait)
        self._pending.pop(0)
        self._deliver(pending.reply)

    def _deliver(self, reply: ScriptedReply) -> None:
        if reply.raises is not None:
            self._inner.fail_next_read(reply.raises, fault=reply.disconnect)
        elif reply.disconnect:
            self._inner.simulate_disconnect()
        if reply.data:
            self._inner.feed(reply.data)

    def _resolve(self, command: str) -> ScriptedReply | None:
        if self._key(command) == self._key(self._error_query):
            return ScriptedReply(data=self._next_error_reply())
        exact = self._exact.get(self._key(command))
        if exact is not None:
            return _normalize(exact.handler(command), self._codec)
        for rule in self._rules:
            if rule.matcher(command):
                return _normalize(rule.handler(command), self._codec)
        if self._unknown_command_error is not None:
            self._state.errors.append(self._unknown_command_error)
        return None

    def _next_error_reply(self) -> bytes:
        error = self._state.errors.pop(0) if self._state.errors else NO_ERROR
        text = f"{error.code},{quote_scpi_string(error.message)}"
        return text.encode(self._codec.encoding) + (self._codec.response_terminator or b"")


def _as_handler(reply: HandlerResult | Handler) -> Handler:
    if callable(reply):
        return reply
    return lambda _command: reply


def _normalize(result: HandlerResult, codec: ScpiTextCodec) -> ScriptedReply | None:
    if result is None:
        return None
    if isinstance(result, ScriptedReply):
        return result
    if isinstance(result, bytes):
        return ScriptedReply(data=result)
    encoded = result.encode(codec.encoding)
    terminator = codec.response_terminator or b""
    if terminator and not encoded.endswith(terminator):
        encoded += terminator
    return ScriptedReply(data=encoded)
