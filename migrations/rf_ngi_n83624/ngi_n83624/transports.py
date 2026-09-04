"""Transport backends for raw SCPI communication with NGI N83624."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .exceptions import CommunicationError, TimeoutError, ValidationError
from .safety import validate_channel, validate_serial_baudrate

from scpi_driver_core import ScpiClient
from scpi_driver_core.exceptions import ScpiDriverError
from scpi_driver_core.exceptions import TransportTimeoutError as CoreTimeout
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import ReadMode, ReadRequest
from scpi_driver_core.transport import SerialTransport as CoreSerialTransport
from scpi_driver_core.transport import TcpTransport as CoreTcpTransport
from scpi_driver_core.transport import UdpTransport as CoreUdpTransport

TERMINATOR = b"\n"

#: This instrument speaks newline-terminated ASCII on all three transports.
_CODEC = ScpiTextCodec(command_terminator=TERMINATOR, response_terminator=TERMINATOR)

#: One newline-terminated reply, bounded.
_LINE = ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=TERMINATOR)

#: As much as has arrived, up to one receive buffer. Used by the TCP read loop.
_UP_TO_CHUNK = ReadRequest(mode=ReadMode.UP_TO_LENGTH, length=4096)

#: One datagram. UDP preserves message boundaries, so no terminator scan.
_DATAGRAM = ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)


def _decode_response(data: bytes, command: str, kind: str) -> str:
    """Decode a reply strictly, then trim padding.

    Strict decoding is deliberate: the pre-migration transports raised on
    non-ASCII rather than silently replacing it, and callers rely on that.
    """
    try:
        return data.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise CommunicationError(
            f"{kind} query returned non-ASCII bytes for command {command!r}"
        ) from exc


@runtime_checkable
class Transport(Protocol):
    """Structural transport protocol used by the driver.

    Third-party transports may be passed to :class:`N83624CellSimulator` without
    inheriting from a base class, as long as they implement this contract.
    """

    def open(self) -> None: ...

    def close(self) -> None: ...

    def write(self, command: str) -> None: ...

    def query(self, command: str) -> str: ...

    def is_open(self) -> bool: ...


@dataclass
class TcpTransport:
    """Raw TCP SCPI transport.

    The vendor manual documents default host ``192.168.0.123`` and TCP port 7000.
    The socket is kept open across commands until ``close()`` is called.
    """

    host: str = "192.168.0.123"
    port: int = 7000
    timeout: float = 3.0
    recv_size: int = 4096

    def __post_init__(self) -> None:
        if self.port <= 0 or self.port > 65535:
            raise ValidationError(f"Invalid TCP port: {self.port}")
        self._client: ScpiClient | None = None

    def open(self) -> None:
        if self._client is not None:
            return
        transport = CoreTcpTransport(host=self.host, port=self.port, timeout_s=self.timeout)
        try:
            transport.open()
        except CoreTimeout as exc:
            raise TimeoutError(f"TCP connect timeout to {self.host}:{self.port}") from exc
        except ScpiDriverError as exc:
            raise CommunicationError(
                f"TCP connect failed to {self.host}:{self.port}: {exc}"
            ) from exc
        self._client = ScpiClient(transport, codec=_CODEC, timeout_s=self.timeout)

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with suppress(Exception):
                client.transport.close()

    def is_open(self) -> bool:
        return self._client is not None

    def write(self, command: str) -> None:
        client = self._require_open()
        payload = _encode_command(command)
        try:
            client.write_bytes(payload)
        except CoreTimeout as exc:
            raise TimeoutError(f"TCP write timeout for command {command!r}") from exc
        except ScpiDriverError as exc:
            self.close()
            raise CommunicationError(f"TCP write failed for command {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        """Send ``command`` and read until a terminator, or until nothing more comes.

        Accumulates as it reads rather than asking for a terminated message in
        one call. The core faults a TCP transport when a read times out, since
        an unterminated stream leaves session validity uncertain, so anything
        already buffered would be unreachable afterwards. Reading incrementally
        keeps this driver's original behaviour: a reply that arrives without a
        terminator is still returned, and only a reply that never starts is a
        timeout.
        """
        client = self._require_open()
        payload = _encode_command(command)
        chunks: list[bytes] = []
        try:
            with client.operation_lock():
                client.write_bytes(payload)
                while True:
                    try:
                        chunk = client.read_bytes(_UP_TO_CHUNK)
                    except CoreTimeout:
                        if chunks:
                            break
                        raise
                    if not chunk:
                        break
                    chunks.append(chunk)
                    if b"\n" in chunk or b"\r" in chunk:
                        break
        except CoreTimeout as exc:
            raise TimeoutError(f"TCP query timeout for command {command!r}") from exc
        except ScpiDriverError as exc:
            self.close()
            raise CommunicationError(f"TCP query failed for command {command!r}: {exc}") from exc
        return _decode_response(b"".join(chunks), command, "TCP")

    def _require_open(self) -> ScpiClient:
        if self._client is None:
            raise CommunicationError("TCP transport is not open")
        return self._client


@dataclass
class UdpTransport:
    """UDP SCPI transport.

    UDP is less reliable than TCP. Use it only when the application can tolerate
    packet loss or when higher measurement acquisition speed is needed.

    Port semantics from the vendor manual:
    - 7000: communication-board port; may control all 24 channels.
    - 7001..7024: channel-specific ports for channels 1..24.

    The high-level driver treats channel-specific UDP ports as single-channel
    transports. It refuses access to other channels unless explicitly bypassed with
    raw SCPI methods.
    """

    host: str = "192.168.0.123"
    port: int = 7000
    timeout: float = 3.0
    recv_size: int = 4096
    single_channel: int | None = None

    def __post_init__(self) -> None:
        if not (7000 <= self.port <= 7024):
            raise ValidationError(f"N83624 UDP port must be 7000..7024; got {self.port}")
        expected_channel = self.port - 7000 if self.port > 7000 else None
        if self.single_channel is None:
            self.single_channel = expected_channel
        elif expected_channel is not None and self.single_channel != expected_channel:
            raise ValidationError(
                f"UDP port {self.port} maps to channel {expected_channel}, not {self.single_channel}"
            )
        if self.single_channel is not None:
            validate_channel(self.single_channel)
        self._client: ScpiClient | None = None

    def open(self) -> None:
        if self._client is not None:
            return
        transport = CoreUdpTransport(host=self.host, port=self.port, timeout_s=self.timeout)
        try:
            transport.open()
        except ScpiDriverError as exc:
            raise CommunicationError(f"UDP socket creation failed: {exc}") from exc
        self._client = ScpiClient(transport, codec=_CODEC, timeout_s=self.timeout)

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with suppress(Exception):
                client.transport.close()

    def is_open(self) -> bool:
        return self._client is not None

    def write(self, command: str) -> None:
        client = self._require_open()
        try:
            client.write_bytes(_encode_command(command))
        except CoreTimeout as exc:
            raise TimeoutError(f"UDP write timeout for command {command!r}") from exc
        except ScpiDriverError as exc:
            raise CommunicationError(f"UDP write failed for command {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        client = self._require_open()
        try:
            with client.operation_lock():
                client.write_bytes(_encode_command(command))
                data = client.read_bytes(_DATAGRAM)
        except CoreTimeout as exc:
            raise TimeoutError(f"UDP query timeout for command {command!r}") from exc
        except ScpiDriverError as exc:
            raise CommunicationError(f"UDP query failed for command {command!r}: {exc}") from exc
        return _decode_response(data, command, "UDP")

    def _require_open(self) -> ScpiClient:
        if self._client is None:
            raise CommunicationError("UDP transport is not open")
        return self._client


@dataclass
class SerialTransport:
    """RS232 SCPI transport using pyserial."""

    port: str
    baudrate: int = 115200
    timeout: float = 3.0

    def __post_init__(self) -> None:
        validate_serial_baudrate(self.baudrate)
        self._client: ScpiClient | None = None

    def open(self) -> None:
        if self._client is not None:
            return
        transport = CoreSerialTransport(
            self.port,
            baudrate=self.baudrate,
            timeout_s=self.timeout,
            write_timeout_s=self.timeout,
        )
        try:
            transport.open()
        except ScpiDriverError as exc:
            # Covers a missing pyserial, which the core reports as a
            # ConfigurationError rather than a bare ImportError.
            raise CommunicationError(f"Serial open failed for {self.port}: {exc}") from exc
        self._client = ScpiClient(transport, codec=_CODEC, timeout_s=self.timeout)

    def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            try:
                client.transport.close()
            except Exception as exc:  # pragma: no cover - backend-dependent edge case
                raise CommunicationError(f"Serial close failed: {exc}") from exc

    def is_open(self) -> bool:
        return self._client is not None and self._client.is_open

    def write(self, command: str) -> None:
        client = self._require_open()
        try:
            client.write_bytes(_encode_command(command))
        except Exception as exc:
            raise CommunicationError(f"Serial write failed for command {command!r}: {exc}") from exc

    def query(self, command: str) -> str:
        client = self._require_open()
        try:
            with client.operation_lock():
                client.write_bytes(_encode_command(command))
                data = client.read_bytes(_LINE)
        except CoreTimeout as exc:
            raise TimeoutError(f"Serial query timeout for command {command!r}") from exc
        except Exception as exc:
            raise CommunicationError(f"Serial query failed for command {command!r}: {exc}") from exc
        if not data:
            raise TimeoutError(f"Serial query timeout for command {command!r}")
        return _decode_response(data, command, "Serial")

    def _require_open(self) -> ScpiClient:
        if self._client is None or not self.is_open():
            raise CommunicationError("Serial transport is not open")
        return self._client


def udp_channel(host: str, channel: int, *, timeout: float = 3.0) -> UdpTransport:
    """Create a UDP transport bound to a channel-specific port.

    ``channel=1`` maps to UDP port 7001, ``channel=24`` maps to 7024.
    The resulting simulator object is intended to access only that channel.
    """
    validate_channel(channel)
    return UdpTransport(host=host, port=7000 + channel, timeout=timeout, single_channel=channel)


def _encode_command(command: str) -> bytes:
    if not isinstance(command, str) or not command.strip():
        raise ValidationError("SCPI command must be a non-empty string")
    command = command.rstrip("\r\n")
    return command.encode("ascii") + TERMINATOR
