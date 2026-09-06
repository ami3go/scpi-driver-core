"""IEEE-488.2 common commands.

These are the starred commands every conforming instrument is supposed to
share. In practice support is uneven, so this class offers them without
requiring any of them: a concrete driver exposes the subset its instrument
actually implements, and nothing here is called automatically.

Nothing in this module is manufacturer-specific. Anything that needs to know
what a particular model does with ``*RST`` belongs in that model's driver.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from scpi_driver_core.exceptions import OperationTimeoutError, TransportTimeoutError
from scpi_driver_core.execution.polling import poll_until
from scpi_driver_core.models import Identity, SelfTestResult
from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.scpi.parsers import parse_identity, parse_int

__all__ = ["OPERATION_COMPLETE_BIT", "CompletionResult", "Ieee4882"]

#: Bit 0 of the standard event status register: Operation Complete.
OPERATION_COMPLETE_BIT = 0x01


@dataclass(frozen=True)
class CompletionResult:
    """How a completion wait went.

    Attributes:
        elapsed_s: how long the wait took.
        polls: how many times ``*ESR?`` was read.
        event_status: every status bit seen while polling, OR-ed together.
            ``*ESR?`` clears the register as it reads it, so bits raised
            part-way through the wait would otherwise be lost. Bits other than
            :data:`OPERATION_COMPLETE_BIT` report errors the instrument
            latched while it worked; bit 5 (``0x20``) is a command error, bit 4
            (``0x10``) an execution error.
    """

    elapsed_s: float
    polls: int
    event_status: int


class Ieee4882:
    """The IEEE-488.2 common command set, over a :class:`ScpiClient`.

    Args:
        client: the client whose transport these commands are sent on.
    """

    def __init__(self, client: ScpiClient) -> None:
        self._client = client

    @property
    def client(self) -> ScpiClient:
        return self._client

    # -- identity ---------------------------------------------------------

    def identify(self, *, timeout_s: float | None = None) -> Identity:
        """Query ``*IDN?`` and parse the reply.

        Validating whether the instrument is the expected one is the concrete
        driver's decision, not this method's.

        Raises:
            IdentityError: if the reply has no manufacturer and model.
        """
        return parse_identity(self._client.query("*IDN?", timeout_s=timeout_s))

    # -- state ------------------------------------------------------------

    def clear_status(self, *, timeout_s: float | None = None) -> None:
        """``*CLS``: clear the status registers and the error queue."""
        self._client.write("*CLS", timeout_s=timeout_s)

    def reset(self, *, timeout_s: float | None = None) -> None:
        """``*RST``: return the instrument to its defined reset state.

        What that state is, and whether reaching it is safe with a load
        connected, is instrument-specific and the driver's responsibility.
        """
        self._client.write("*RST", timeout_s=timeout_s)

    # -- synchronization --------------------------------------------------

    def operation_complete(self, *, timeout_s: float | None = None) -> bool:
        """``*OPC?``: whether pending operations have finished.

        The instrument holds the response until it is done, so this waits for
        the client's timeout rather than answering immediately. Use
        :meth:`wait_operation_complete` when the wait needs its own bound.
        """
        return parse_int(self._client.query("*OPC?", timeout_s=timeout_s)) == 1

    def wait_operation_complete(self, timeout_s: float) -> None:
        """``*OPC?``: block until pending operations finish, within ``timeout_s``.

        Args:
            timeout_s: the bound for this wait, typically longer than the
                client default because the operation being waited on is slow.

        Raises:
            OperationTimeoutError: if the instrument does not report completion
                in time. The underlying transport timeout is chained as the
                cause.
        """
        try:
            response = self._client.query("*OPC?", timeout_s=timeout_s)
        except TransportTimeoutError as exc:
            raise OperationTimeoutError(f"operation did not complete within {timeout_s}s") from exc
        if parse_int(response) != 1:
            raise OperationTimeoutError(f"*OPC? reported {response!r} rather than completion")

    def set_operation_complete(self, *, timeout_s: float | None = None) -> None:
        """``*OPC``: set the completion bit in the event status register.

        Unlike :meth:`operation_complete` this does not wait; it arms the bit
        that :meth:`read_event_status` will later report.
        """
        self._client.write("*OPC", timeout_s=timeout_s)

    def wait_for_completion(
        self,
        *,
        timeout_s: float,
        interval_s: float = 0.05,
        backoff: float = 1.5,
        maximum_interval_s: float | None = 1.0,
        poll_timeout_s: float | None = None,
        arm: bool = True,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> CompletionResult:
        """Wait for a slow operation by polling ``*ESR?``, without blocking on it.

        This is the way to wait out an instrument that takes minutes to answer.
        The obvious alternatives both break the connection:

        * A long read (``*OPC?``, or just the slow query itself) holds the link
          silent for the whole operation. If the estimate is short by a second
          the read times out, and a timed-out read is unrecoverable in a
          well-behaved transport: the reply is still in flight, so it would be
          returned as the answer to whatever is asked next. The transport
          therefore faults, and the session is over.
        * Retrying that read with a longer timeout has the same problem one
          step later — there is no live connection left to retry on.

        Polling avoids both. ``*OPC`` returns immediately and arms bit 0 of the
        event status register when the pending work finishes, and ``*ESR?``
        answers immediately even while the instrument is busy. So every read
        here is short and expected to succeed, the link is never left silent,
        and a wait that runs over its deadline raises without having damaged
        anything: the connection is still open and the instrument still usable.

        The interval grows by ``backoff`` after each poll, up to
        ``maximum_interval_s``. A fast operation is noticed almost at once
        while a long one is not polled thousands of times.

        Args:
            timeout_s: total bound for the wait. Measured on a monotonic clock.
            interval_s: pause before the second poll.
            backoff: multiplier applied to the interval after each poll. Pass
                ``1.0`` to poll at a fixed rate.
            maximum_interval_s: ceiling for the growing interval, or ``None``
                to let it grow unbounded.
            poll_timeout_s: per-query timeout for ``*OPC`` and ``*ESR?``. These
                are answered immediately, so the client default is normally
                right; this is not the operation's timeout.
            arm: whether to send ``*OPC`` first. Pass ``False`` if the caller
                already sent it, or sent a command that arms the bit itself.
            clock: monotonic time source; injectable for deterministic tests.
            sleep: how to pause; injectable for the same reason, and so a
                caller can substitute an interruptible sleep.

        Returns:
            The elapsed time, the number of polls, and the OR of every status
            byte seen. Inspect ``event_status`` for error bits: the instrument
            reports "finished" the same way whether or not it succeeded.

        Raises:
            OperationTimeoutError: if the completion bit is not set within
                ``timeout_s``, or if a status poll itself times out. The first
                case leaves the connection open and usable; the second means
                the instrument stopped answering entirely, and the transport
                fault is chained as the cause.
        """
        if arm:
            self.set_operation_complete(timeout_s=poll_timeout_s)

        observed = 0

        def complete() -> bool:
            nonlocal observed
            try:
                status = self.read_event_status(timeout_s=poll_timeout_s)
            except TransportTimeoutError as exc:
                # *ESR? is answered even by a busy instrument, so a timeout
                # here is not slowness; the instrument has stopped talking.
                # Polling on is pointless: the transport has faulted.
                raise OperationTimeoutError(
                    "*ESR? did not answer while waiting for operation complete; "
                    "the instrument stopped responding to status polls"
                ) from exc
            observed |= status
            return bool(status & OPERATION_COMPLETE_BIT)

        result = poll_until(
            complete,
            timeout_s=timeout_s,
            interval_s=interval_s,
            backoff=backoff,
            maximum_interval_s=maximum_interval_s,
            clock=clock,
            sleep=sleep,
            description="operation complete (*OPC armed, *ESR? bit 0)",
        )
        return CompletionResult(
            elapsed_s=result.elapsed_s, polls=result.attempts, event_status=observed
        )

    def run_until_complete(
        self,
        command: str,
        *,
        timeout_s: float,
        clear_first: bool = True,
        interval_s: float = 0.05,
        backoff: float = 1.5,
        maximum_interval_s: float | None = 1.0,
        poll_timeout_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> CompletionResult:
        """Send a slow command and wait for it, polling rather than blocking.

        The full ``*CLS`` / command / ``*OPC`` / poll ``*ESR?`` sequence. Use it
        for the commands that take far longer than a normal reply: sweeps,
        long integrations, calibration, ranging on a supply or load.

        ``command`` must be a command, not a query. A query's reply would still
        be sitting in the instrument's output buffer when this returns, and the
        next read would collect it as an answer to something else.

        Args:
            command: the slow command to send.
            timeout_s: total bound for the wait that follows it.
            clear_first: send ``*CLS`` before the command. This clears the
                event status register, so a completion bit left over from an
                earlier operation cannot end this wait immediately. It also
                empties the error queue, which is why it can be turned off.
            interval_s: pause before the second poll.
            backoff: multiplier applied to the interval after each poll.
            maximum_interval_s: ceiling for the growing interval.
            poll_timeout_s: per-query timeout for the short commands. The slow
                command is sent with it too — sending is fast, only the
                instrument's processing is slow.
            clock: monotonic time source; injectable for tests.
            sleep: how to pause; injectable for the same reason.

        Returns:
            The same report as :meth:`wait_for_completion`.

        Raises:
            OperationTimeoutError: if the operation does not finish in time.
                The connection is left open, so the caller can query the error
                queue or abort.
        """
        if clear_first:
            self.clear_status(timeout_s=poll_timeout_s)
        self._client.write(command, timeout_s=poll_timeout_s)
        return self.wait_for_completion(
            timeout_s=timeout_s,
            interval_s=interval_s,
            backoff=backoff,
            maximum_interval_s=maximum_interval_s,
            poll_timeout_s=poll_timeout_s,
            clock=clock,
            sleep=sleep,
        )

    def wait(self, *, timeout_s: float | None = None) -> None:
        """``*WAI``: make the instrument finish pending operations before more.

        This returns as soon as the command is sent. The sequencing happens
        inside the instrument, so nothing is read back.
        """
        self._client.write("*WAI", timeout_s=timeout_s)

    def trigger(self, *, timeout_s: float | None = None) -> None:
        """``*TRG``: send a bus trigger."""
        self._client.write("*TRG", timeout_s=timeout_s)

    # -- diagnostics ------------------------------------------------------

    def self_test(self, *, timeout_s: float | None = None) -> SelfTestResult:
        """``*TST?``: run the internal self-test.

        Self-tests are often slow, so pass a ``timeout_s`` well above the
        client default. The result is reported, not raised on: whether a
        non-zero code should fail a test run is the caller's policy.
        """
        raw = self._client.query("*TST?", timeout_s=timeout_s)
        return SelfTestResult(code=parse_int(raw), raw=raw)

    def read_status_byte(self, *, timeout_s: float | None = None) -> int:
        """``*STB?``: read the status byte register."""
        return parse_int(self._client.query("*STB?", timeout_s=timeout_s))

    def read_event_status(self, *, timeout_s: float | None = None) -> int:
        """``*ESR?``: read and clear the standard event status register."""
        return parse_int(self._client.query("*ESR?", timeout_s=timeout_s))
