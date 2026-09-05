"""Transport layer: VISA (via ``scpi-driver-core``) and the in-process simulator.

Per RFDS-004, protocol/driver code never touches pyvisa directly outside
this module. Unlike ``rf_tbs1000c``, GPIB/USB/LAN are all standard on this
instrument and all reachable through one VISA resource string, so there is
only one hardware backend here, not one per interface (task §5.1). Every
command this driver issues is plain text — arbitrary waveform data is sent
as ASCII comma-separated values (documented as an accepted alternative to
an IEEE binary block for both ``DATA`` and ``DATA:DAC``), so no binary
transport path is needed for Gate 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from scpi_driver_core import ScpiClient
from scpi_driver_core.exceptions import ScpiDriverError
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import VisaTransport

from .exceptions import Agilent33220AConnectionError, Agilent33220ATimeoutError

if TYPE_CHECKING:
    from .simulator import SimAgilent33220AInstrument


#: The 33220A speaks newline-terminated ASCII.
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
    """VISA transport — GPIB, USB, or LAN, chosen by ``resource``'s prefix.

    PyVISA is loaded by the core and only when :meth:`open` is called, so this
    package stays importable without it when only the simulator is used. No
    device I/O happens at import or construction time either way.
    """

    def __init__(self, resource: str, timeout_s: float = 5.0) -> None:
        if not resource or not str(resource).strip():
            raise Agilent33220AConnectionError("a VISA resource string is required")
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
            raise Agilent33220AConnectionError(
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
            raise Agilent33220AConnectionError("transport is not open")
        return self._client

    def write(self, command: str) -> None:
        """Send a command, expecting no reply."""
        client = self._require_open()
        try:
            client.write(command)
        except ScpiDriverError as exc:
            raise Agilent33220ATimeoutError(f"write failed for {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        """Send a query and return its reply."""
        client = self._require_open()
        try:
            return client.query(command).strip()
        except ScpiDriverError as exc:
            raise Agilent33220ATimeoutError(f"query failed for {command!r}: {exc}") from exc

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
    """Wraps a :class:`~agilent33220a.simulator.SimAgilent33220AInstrument`.

    Every command — write or query — goes through the simulator's single
    ``dispatch`` entry point, so the real SCPI strings built by
    ``driver.py`` are exercised exactly as they would be against hardware.
    """

    def __init__(self, simulator: SimAgilent33220AInstrument | None = None) -> None:
        if simulator is None:
            from .simulator import SimAgilent33220AInstrument

            simulator = SimAgilent33220AInstrument()
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
            raise Agilent33220AConnectionError("transport is not open")

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
    def simulator(self) -> SimAgilent33220AInstrument:
        """Direct access for tests that need to inspect/drive simulator state."""
        return self._simulator
