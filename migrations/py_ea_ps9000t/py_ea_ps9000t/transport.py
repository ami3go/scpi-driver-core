"""Transport layer: VISA (via ``scpi-driver-core``) and the in-process simulator.

Per RFDS-004, protocol/driver code never touches pyvisa directly outside
this module. USB, RS232, and Ethernet are all addressable as VISA resource
strings, so there is only one hardware backend here, not one per interface
(task §5) — the same single-VISA-backend precedent already established for
``agilent33220a``/``agilent34411a``. This device also speaks ModBus RTU on
the same physical port, disambiguated by a leading 0x00 byte; this driver
never sends that byte, so it is unconditionally speaking SCPI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from scpi_driver_core import ScpiClient
from scpi_driver_core.exceptions import ScpiDriverError
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import VisaTransport

from .exceptions import EaPs9000TConnectionError, EaPs9000TTimeoutError

if TYPE_CHECKING:
    from .simulator import SimEaPs9000TInstrument


#: The PS 9000 T speaks newline-terminated ASCII.
_CODEC = ScpiTextCodec(command_terminator=b"\n", response_terminator=b"\n")


class Transport(Protocol):
    """Text-oriented boundary every backend implements identically."""

    resource: str

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_open(self) -> bool: ...

    def write(self, command: str) -> None: ...

    def query(self, command: str) -> str: ...

    @property
    def timeout_s(self) -> float: ...

    @timeout_s.setter
    def timeout_s(self, value: float) -> None: ...


class PyvisaTransport:
    """VISA transport, built on the core's VISA backend.

    PyVISA is loaded by the core and only when :meth:`open` is called, so this
    package stays importable without it when only the simulator is used. No
    device I/O happens at import or construction time either way.
    """

    def __init__(self, resource: str, timeout_s: float = 5.0) -> None:
        if not resource or not str(resource).strip():
            raise EaPs9000TConnectionError("a VISA resource string is required")
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
            raise EaPs9000TConnectionError(
                f"could not open VISA resource {self.resource!r}: {exc}"
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
            raise EaPs9000TConnectionError("transport is not open")
        return self._client

    def write(self, command: str) -> None:
        """Send a command, expecting no reply."""
        client = self._require_open()
        try:
            client.write(command)
        except ScpiDriverError as exc:
            raise EaPs9000TTimeoutError(f"write failed for {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        """Send a query and return its reply."""
        client = self._require_open()
        try:
            return client.query(command).strip()
        except ScpiDriverError as exc:
            raise EaPs9000TTimeoutError(f"query failed for {command!r}: {exc}") from exc

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
    """Wraps a :class:`~py_ea_ps9000t.simulator.SimEaPs9000TInstrument`.

    Every command — write or query — goes through the simulator's single
    ``dispatch`` entry point, so the real SCPI strings built by
    ``driver.py`` are exercised exactly as they would be against hardware.
    """

    def __init__(self, simulator: SimEaPs9000TInstrument | None = None) -> None:
        if simulator is None:
            from .simulator import SimEaPs9000TInstrument

            simulator = SimEaPs9000TInstrument()
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
            raise EaPs9000TConnectionError("transport is not open")

    def write(self, command: str) -> None:
        """Send a command, expecting no reply."""
        self._require_open()
        self._simulator.dispatch(command)

    def query(self, command: str) -> str:
        """Send a query and return its reply."""
        self._require_open()
        return self._simulator.dispatch(command).decode("ascii", errors="replace").strip()

    @property
    def timeout_s(self) -> float:
        """The timeout in seconds."""
        return self._timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        """The timeout in seconds."""
        self._timeout_s = float(value)

    @property
    def simulator(self) -> SimEaPs9000TInstrument:
        """Direct access for tests that need to inspect/drive simulator state."""
        return self._simulator
