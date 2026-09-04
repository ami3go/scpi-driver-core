"""A scripted SCPI instrument, for driver tests without hardware.

:class:`~scpi_driver_core.transport.mock.MockTransport` answers in bytes and
knows nothing about commands. This transport sits at the command level: it
decodes each write as a SCPI command, finds a handler, and queues that
handler's reply for the next read.

It composes ``MockTransport`` rather than reimplementing it, so the transport
state machine, read modes, and bounded-read guarantees are the same ones the
conformance suite already checks.

This is the reusable substrate. A simulator for a particular instrument, with
its command tree and its physical model, belongs in that instrument's own
package and builds on this.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Union

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.models import ScpiError
from scpi_driver_core.scpi.binary_block import encode_definite_length_block
from scpi_driver_core.scpi.codec import ScpiTextCodec
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
"""What a real instrument queues when it does not recognize a command."""

#: What a handler may return: text, raw bytes, a full reply, or nothing.
HandlerResult = Union[str, bytes, "ScriptedReply", None]
Handler = Callable[[str], HandlerResult]


@dataclass(frozen=True)
class ScriptedReply:
    """What the simulated instrument does in response to one command.

    Args:
        data: bytes queued for the next read. Empty for a command that answers
            nothing, as most non-query commands do.
        delay_s: how long the instrument appears to take before replying.
        raises: armed so the *next read* fails with this, rather than the
            write. That is where a real instrument's silence shows up.
        disconnect: drop the connection. Combined with ``raises`` it decides
            whether the transport also faults.
    """

    data: bytes = b""
    delay_s: float = 0.0
    raises: Exception | None = None
    disconnect: bool = False


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


class ScriptedScpiTransport:
    """A transport that answers SCPI commands from a script.

    Args:
        codec: how commands are decoded and replies framed. Must match what the
            driver under test uses, or nothing will line up.
        descriptor: identity reported by the transport.
        error_query: the command answered from the simulated error queue.
        unknown_command_error: pushed onto that queue when a command matches no
            handler, the way a real instrument reports an unrecognized header.
            Set it to ``None`` to let unknown commands pass silently.
        sleep: how a scripted delay is served; injectable so tests need not
            really wait.

    Raises:
        ConfigurationError: if the codec has no command terminator, since
            commands could then not be told apart.
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
        )
        self._error_query = error_query
        self._unknown_command_error = unknown_command_error
        self._sleep = sleep
        self._exact: dict[str, _ExactRule] = {}
        self._rules: list[_Rule] = []
        self._state = _State()

    # -- scripting --------------------------------------------------------

    def on(self, command: str, reply: HandlerResult | Handler = None) -> ScriptedScpiTransport:
        """Answer an exact command.

        Matching ignores surrounding whitespace and case, as an instrument
        does. Returns self, so registrations can be chained.

        Args:
            command: the command text, without a terminator.
            reply: text, bytes, a :class:`ScriptedReply`, or a callable taking
                the command and returning one of those.
        """
        self._exact[self._key(command)] = _ExactRule(
            handler=_as_handler(reply), description=command
        )
        return self

    def on_regex(
        self, pattern: str | re.Pattern[str], reply: HandlerResult | Handler = None
    ) -> ScriptedScpiTransport:
        """Answer any command matching ``pattern``.

        Patterns are tried in registration order, after exact matches. The
        search is case-insensitive unless the pattern was compiled otherwise.
        """
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
        """Answer any command for which ``predicate`` is true."""
        self._rules.append(
            _Rule(matcher=predicate, handler=_as_handler(reply), description="predicate")
        )
        return self

    def reply_block(self, command: str, payload: bytes) -> ScriptedScpiTransport:
        """Answer ``command`` with ``payload`` as a definite-length block.

        The block header and the response terminator are added here, so a test
        supplies only the payload it expects the driver to recover.
        """
        return self.on(command, self.block(payload))

    def block(self, payload: bytes) -> bytes:
        """Frame ``payload`` as a terminated definite-length block."""
        return encode_definite_length_block(payload) + (self._codec.response_terminator or b"")

    # -- the simulated error queue ----------------------------------------

    def push_error(self, error: ScpiError) -> None:
        """Queue an error for the next error query, as a real instrument would."""
        self._state.errors.append(error)

    @property
    def pending_errors(self) -> list[ScpiError]:
        return list(self._state.errors)

    # -- inspection -------------------------------------------------------

    @property
    def history(self) -> list[str]:
        """Every command received, in order, decoded and stripped."""
        return list(self._state.history)

    def clear_history(self) -> None:
        self._state.history.clear()

    @property
    def inner(self) -> MockTransport:
        """The byte-level transport underneath, for failure injection."""
        return self._inner

    # -- Transport protocol -----------------------------------------------

    @property
    def state(self) -> TransportState:
        return self._inner.state

    @property
    def is_open(self) -> bool:
        return self._inner.is_open

    @property
    def descriptor(self) -> TransportDescriptor:
        return self._inner.descriptor

    def open(self) -> TransportDescriptor:
        return self._inner.open()

    def close(self) -> None:
        self._inner.close()

    def write(
        self,
        data: bytes,
        *,
        timeout_s: float | None = None,
        operation_id: str | None = None,
    ) -> WriteResult:
        """Accept a command and queue whatever the script says to answer."""
        result = self._inner.write(data, timeout_s=timeout_s, operation_id=operation_id)
        command = self._decode(data)
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
        return self._inner.read(request, timeout_s=timeout_s, operation_id=operation_id)

    def transact(
        self,
        outbound: bytes,
        response: ReadRequest,
        *,
        timeout_s: float | None = None,
        replay_policy: ReplayPolicy = ReplayPolicy.NEVER,
        operation_id: str | None = None,
    ) -> bytes:
        with self._inner.operation_lock():
            self.write(outbound, timeout_s=timeout_s, operation_id=operation_id)
            return self.read(response, timeout_s=timeout_s, operation_id=operation_id)

    def flush(self, direction: FlushDirection) -> None:
        self._inner.flush(direction)

    # -- internals --------------------------------------------------------

    def _decode(self, data: bytes) -> str:
        payload = data
        terminator = self._codec.command_terminator
        if terminator and payload.endswith(terminator):
            payload = payload[: -len(terminator)]
        return payload.decode(self._codec.encoding, errors="replace").strip()

    def _key(self, command: str) -> str:
        return command.strip().casefold()

    def _serve(self, command: str) -> None:
        """Resolve ``command`` and queue or arm its effect."""
        reply = self._resolve(command)
        if reply is None:
            return
        if reply.delay_s > 0:
            self._sleep(reply.delay_s)
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
        text = f'{error.code},"{error.message}"'
        return text.encode(self._codec.encoding) + (self._codec.response_terminator or b"")


def _as_handler(reply: HandlerResult | Handler) -> Handler:
    if callable(reply):
        return reply
    return lambda _command: reply


def _normalize(result: HandlerResult, codec: ScpiTextCodec) -> ScriptedReply | None:
    """Turn whatever a handler returned into a reply, framing text."""
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
