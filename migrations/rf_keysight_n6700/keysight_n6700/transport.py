"""Transport adapters over ``scpi-driver-core``.

Before the migration this module hand-rolled a PyVISA wrapper, a raw-socket
wrapper, and a simulator wrapper: roughly 200 lines of connection lifecycle,
locking, framing and error translation that every other driver in the fleet had
also written for itself.

That infrastructure now comes from ``scpi_driver_core``. What remains here is
an adapter: the driver was written against a ``write(str)`` / ``query(str)``
interface, and preserving that interface is what keeps this a migration rather
than a rewrite. Everything above this file, all of the N6700 command tree and
channel logic, is untouched.

The core's boundary is bytes, which is what makes the definite-length block
reads in :mod:`keysight_n6700.datalog` sound; this adapter puts the text
convenience back on top for the command paths that only ever handled text.
"""

from __future__ import annotations

import threading
from typing import Any, Protocol, runtime_checkable

from scpi_driver_core import ScpiClient
from scpi_driver_core.exceptions import (
    ConfigurationError,
    ScpiDriverError,
    TransportTimeoutError,
)
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import (
    ReadMode,
    ReadRequest,
    TcpTransport,
    VisaTransport,
)

from .exceptions import N6700ConnectionError, N6700TimeoutError, UnsupportedFeatureError

#: The N6700 speaks newline-terminated ASCII on every transport it supports.
_CODEC = ScpiTextCodec(command_terminator=b"\n", response_terminator=b"\n")


@runtime_checkable
class Transport(Protocol):
    supports_clear: bool

    @property
    def is_open(self) -> bool: ...
    def write(self, command: str) -> None: ...
    def query(self, command: str) -> str: ...
    def read_raw(self) -> bytes: ...
    def write_raw(self, data: bytes) -> None: ...
    def clear(self) -> None: ...
    def close(self) -> None: ...


class _CoreTransportAdapter:
    """Presents the driver's text interface over a core transport.

    Translation of core exceptions into the N6700 hierarchy happens here, in
    one place, rather than being repeated per backend as it used to be.
    """

    supports_clear = False

    def __init__(self, client: ScpiClient, *, description: str) -> None:
        self._client = client
        self._description = description
        self._lock = threading.RLock()

    @property
    def client(self) -> ScpiClient:
        """The underlying core client, for code that wants bytes rather than text."""
        return self._client

    @property
    def is_open(self) -> bool:
        return self._client.is_open

    def write(self, command: str) -> None:
        with self._lock, self._translating("write"):
            self._client.write(command)

    def query(self, command: str) -> str:
        with self._lock, self._translating("query"):
            # The core strips only the configured terminator, never arbitrary
            # whitespace. N6700 firmware pads some replies, and the driver has
            # always trimmed that, so the trimming lives here: it is this
            # instrument's tolerance, not a protocol rule.
            return self._client.query(command).strip()

    def read_raw(self) -> bytes:
        with self._lock, self._translating("read"):
            request = ReadRequest(
                mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n", include_terminator=True
            )
            return self._client.read_bytes(request)

    def write_raw(self, data: bytes) -> None:
        with self._lock, self._translating("write"):
            self._client.write_bytes(data)

    def clear(self) -> None:
        raise UnsupportedFeatureError(f"{self._description} does not support device clear")

    def close(self) -> None:
        with self._lock:
            self._client.transport.close()

    def _translating(self, operation: str) -> Any:
        return _Translating(operation, self._description)


class _Translating:
    """Maps core errors onto the driver's own exception vocabulary."""

    def __init__(self, operation: str, description: str) -> None:
        self._operation = operation
        self._description = description

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> bool:
        if exc is None:
            return False
        if isinstance(exc, TransportTimeoutError):
            raise N6700TimeoutError(f"{self._operation} timed out: {exc}") from exc
        if isinstance(exc, ScpiDriverError):
            raise N6700ConnectionError(f"{self._operation} failed: {exc}") from exc
        return False


class PyVisaTransport(_CoreTransportAdapter):
    """VISA transport for USBTMC, TCPIP INSTR, and TCPIP SOCKET resources.

    Terminations are handled by the codec above the byte transport rather than
    by PyVISA, so binary block reads are no longer at the mercy of a
    ``read_termination`` that would trim payload bytes.
    """

    supports_clear = True

    def __init__(
        self,
        resource: str,
        *,
        timeout_ms: int = 5000,
        read_termination: str = "\n",
        write_termination: str = "\n",
        query_delay: float | None = None,
        chunk_size: int | None = None,
        backend: str | None = None,
    ) -> None:
        del query_delay  # PyVISA-specific pacing; unused by the core path
        codec = ScpiTextCodec(
            command_terminator=write_termination.encode("ascii"),
            response_terminator=read_termination.encode("ascii") or None,
        )
        try:
            transport = VisaTransport(
                resource,
                timeout_s=timeout_ms / 1000.0,
                visa_library=backend or "",
                **({"chunk_size": chunk_size} if chunk_size else {}),
            )
            transport.open()
        except ConfigurationError as exc:
            raise N6700ConnectionError(str(exc)) from exc
        except ScpiDriverError as exc:
            raise N6700ConnectionError(f"could not open VISA resource {resource!r}") from exc

        self.resource = resource
        super().__init__(
            ScpiClient(transport, codec=codec), description=f"VISA resource {resource!r}"
        )

    def clear(self) -> None:
        from scpi_driver_core.transport import FlushDirection

        with self._lock, self._translating("clear"):
            self._client.transport.flush(FlushDirection.BOTH)


class RawSocketTransport(_CoreTransportAdapter):
    """Raw TCP SCPI socket transport.

    Device clear is not faked over raw sockets. ``supports_clear`` is False.
    """

    supports_clear = False

    def __init__(self, host: str, port: int = 5025, *, timeout_s: float = 5.0) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        try:
            transport = TcpTransport(host=host, port=port, timeout_s=timeout_s)
            transport.open()
        except ScpiDriverError as exc:
            raise N6700ConnectionError(f"could not connect to {host}:{port}") from exc
        super().__init__(ScpiClient(transport, codec=_CODEC), description=f"socket {host}:{port}")


class SimulatedTransport:
    """Transport for the built-in simulator.

    Left as it was. The simulator models N6700 behavior, which is device
    semantics and therefore out of scope for the core; migrating it would be a
    rewrite rather than an extraction.
    """

    supports_clear = True

    def __init__(self, simulator: object) -> None:
        self.simulator = simulator
        self._lock = threading.RLock()
        self._open = True
        self._raw_response = b""

    @property
    def is_open(self) -> bool:
        return self._open

    def write(self, command: str) -> None:
        with self._lock:
            self.simulator.execute(command)  # type: ignore[attr-defined]

    def query(self, command: str) -> str:
        with self._lock:
            response = self.simulator.execute(command)  # type: ignore[attr-defined]
            if isinstance(response, bytes):
                return response.decode("ascii", errors="replace").strip()
            return str(response).strip()

    def read_raw(self) -> bytes:
        with self._lock:
            return self._raw_response

    def write_raw(self, data: bytes) -> None:
        with self._lock:
            self._raw_response = data

    def clear(self) -> None:
        with self._lock:
            self.simulator.clear()  # type: ignore[attr-defined]

    def close(self) -> None:
        self._open = False
