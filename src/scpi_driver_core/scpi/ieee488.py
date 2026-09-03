"""IEEE-488.2 common commands.

These are the starred commands every conforming instrument is supposed to
share. In practice support is uneven, so this class offers them without
requiring any of them: a concrete driver exposes the subset its instrument
actually implements, and nothing here is called automatically.

Nothing in this module is manufacturer-specific. Anything that needs to know
what a particular model does with ``*RST`` belongs in that model's driver.
"""

from __future__ import annotations

from scpi_driver_core.exceptions import OperationTimeoutError, TransportTimeoutError
from scpi_driver_core.models import Identity, SelfTestResult
from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.scpi.parsers import parse_identity, parse_int

__all__ = ["Ieee4882"]


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
