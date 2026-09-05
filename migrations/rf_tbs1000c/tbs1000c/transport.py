"""Transport layer: USBTMC (via ``scpi-driver-core``) and the in-process simulator.

Per RFDS-004, protocol/driver code never touches pyvisa/usb directly outside
this module. Both backends expose the same three operations so ``driver.py``
never needs to know which one it's talking to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from scpi_driver_core import ScpiClient
from scpi_driver_core.exceptions import ScpiDriverError
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import ReadMode, ReadRequest, VisaTransport

from .exceptions import Tbs1000cConnectionError, Tbs1000cTimeoutError

if TYPE_CHECKING:
    from .simulator import SimTbs1000cInstrument


#: The TBS1000C speaks newline-terminated ASCII for text commands.
_CODEC = ScpiTextCodec(command_terminator=b"\n", response_terminator=b"\n")

#: One whole USBTMC message, which is how a CURVe? payload arrives.
_MESSAGE = ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE, maximum_size=64 * 1024 * 1024)


class Transport(Protocol):
    """Byte-oriented boundary every backend implements identically."""

    resource: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_open(self) -> bool: ...

    def write(self, command: str) -> None: ...

    def write_binary(self, command_prefix: str, data: bytes) -> None: ...

    def query(self, command: str) -> str: ...

    def query_binary(self, command: str) -> bytes: ...

    @property
    def timeout_s(self) -> float: ...

    @timeout_s.setter
    def timeout_s(self, value: float) -> None: ...


class PyvisaUsbtmcTransport:
    """USBTMC transport, built on the core's VISA backend.

    PyVISA is loaded by the core and only when :meth:`open` is called, so this
    package stays importable without it when only the simulator is used. No
    device I/O happens at import or construction time either way.

    The binary paths matter most on this instrument. ``CURVe?`` and
    ``FILESystem:READFile?`` return raw sample bytes in which 0x0A and 0x20 are
    ordinary data, so the core is configured with terminations disabled and the
    payload is read as one VISA message. Nothing between the instrument and
    :func:`tbs1000c.codec.parse_curve_response` inspects or trims a sample byte.
    """

    def __init__(self, resource: str, timeout_s: float = 5.0) -> None:
        if not resource or not str(resource).strip():
            raise Tbs1000cConnectionError("a VISA resource string is required for USBTMC")
        self.resource = str(resource).strip()
        self._timeout_s = float(timeout_s)
        self._client: ScpiClient | None = None

    @property
    def client(self) -> ScpiClient | None:
        """The core client, for code that wants bytes rather than text."""
        return self._client

    def open(self) -> None:
        """Open the connection."""
        try:
            transport = VisaTransport(self.resource, timeout_s=self._timeout_s)
            transport.open()
        except ScpiDriverError as exc:
            # ConfigurationError covers a missing PyVISA, which used to be a
            # separate ImportError branch here.
            raise Tbs1000cConnectionError(
                f"could not open USBTMC resource {self.resource!r}: {exc}"
            ) from exc
        self._client = ScpiClient(transport, codec=_CODEC, timeout_s=self._timeout_s)

    def close(self) -> None:
        """Close the connection and release the transport."""
        if self._client is not None:
            self._client.transport.close()
            self._client = None

    def is_open(self) -> bool:
        """Whether the open."""
        return self._client is not None

    def _require_open(self) -> ScpiClient:
        if self._client is None:
            raise Tbs1000cConnectionError("transport is not open")
        return self._client

    def write(self, command: str) -> None:
        """Send a command, expecting no reply."""
        client = self._require_open()
        try:
            client.write(command)
        except ScpiDriverError as exc:
            raise Tbs1000cTimeoutError(f"write failed for {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        """Send a query and return its reply."""
        client = self._require_open()
        try:
            return client.query(command).strip()
        except ScpiDriverError as exc:
            raise Tbs1000cTimeoutError(f"query failed for {command!r}: {exc}") from exc

    def query_binary(self, command: str) -> bytes:
        """Read one whole VISA message, byte for byte.

        The block header is left in place: :func:`parse_curve_response` accepts
        either the binary block or the ASCII form, and only it can tell which
        arrived.
        """
        client = self._require_open()
        try:
            with client.operation_lock():
                client.write(command)
                return client.read_bytes(_MESSAGE)
        except ScpiDriverError as exc:
            raise Tbs1000cTimeoutError(f"binary query failed for {command!r}: {exc}") from exc

    def write_binary(self, command_prefix: str, data: bytes) -> None:
        """Sends ``command_prefix`` immediately followed by ``data`` (already IEEE-488.2
        block-encoded by the caller) and a terminator — used for ``FILESystem:WRITEFile``."""

        client = self._require_open()
        try:
            client.write_bytes(client.codec.encode_block_command(command_prefix, data))
        except ScpiDriverError as exc:
            raise Tbs1000cTimeoutError(f"binary write failed for {command_prefix!r}: {exc}") from exc

    @property
    def timeout_s(self) -> float:
        """The timeout in seconds."""
        return self._timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        """The timeout in seconds."""
        self._timeout_s = float(value)
        if self._client is not None:
            self._client.set_timeout(self._timeout_s)


class SimulatedTransport:
    """Wraps a :class:`~tbs1000c.simulator.SimTbs1000cInstrument`.

    Every command — write or query, text or binary — goes through the
    simulator's single ``dispatch`` entry point, so the real SCPI strings
    built by ``driver.py`` are exercised exactly as they would be against
    hardware; nothing here special-cases individual commands.
    """

    def __init__(self, simulator: SimTbs1000cInstrument | None = None) -> None:
        if simulator is None:
            from .simulator import SimTbs1000cInstrument

            simulator = SimTbs1000cInstrument()
        self._simulator = simulator
        self.resource = "SIM::default"
        self._open = False
        self._timeout_s = 5.0

    def open(self) -> None:
        """Open the connection."""
        self._open = True

    def close(self) -> None:
        """Close the connection and release the transport."""
        self._open = False

    def is_open(self) -> bool:
        """Whether the open."""
        return self._open

    def _require_open(self) -> None:
        if not self._open:
            raise Tbs1000cConnectionError("transport is not open")

    def write(self, command: str) -> None:
        """Send a command, expecting no reply."""
        self._require_open()
        self._simulator.dispatch(command)

    def query(self, command: str) -> str:
        """Send a query and return its reply."""
        self._require_open()
        return self._simulator.dispatch(command).decode("ascii", errors="replace").strip()

    def query_binary(self, command: str) -> bytes:
        """Query the binary."""
        self._require_open()
        return self._simulator.dispatch(command)

    def write_binary(self, command_prefix: str, data: bytes) -> None:
        """Write the binary."""
        self._require_open()
        self._simulator.dispatch_binary(command_prefix, data)

    @property
    def timeout_s(self) -> float:
        """The timeout in seconds."""
        return self._timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        """The timeout in seconds."""
        self._timeout_s = float(value)

    @property
    def simulator(self) -> SimTbs1000cInstrument:
        """Direct access for tests that need to inspect/drive simulator state."""
        return self._simulator
