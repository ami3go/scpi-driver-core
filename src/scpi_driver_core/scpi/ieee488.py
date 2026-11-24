"""IEEE-488.2 common commands and optional IEEE-488.1 transport capabilities."""

from __future__ import annotations

from scpi_driver_core.exceptions import (
    ConfigurationError,
    OperationTimeoutError,
    ResponseParseError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.models import Identity, SelfTestResult
from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.scpi.parsers import parse_identity, parse_int

__all__ = ["Ieee4882"]


class Ieee4882:
    def __init__(self, client: ScpiClient) -> None:
        self._client = client

    @property
    def client(self) -> ScpiClient:
        return self._client

    def identify(self, *, timeout_s: float | None = None) -> Identity:
        return parse_identity(self.identify_raw(timeout_s=timeout_s))

    def identify_raw(self, *, timeout_s: float | None = None) -> str:
        """Raw IDN response, without imposing a parsed-identity contract."""
        return self._client.query("*IDN?", timeout_s=timeout_s)

    def clear_status(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*CLS", timeout_s=timeout_s)

    def reset(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*RST", timeout_s=timeout_s)

    def operation_complete(self, *, timeout_s: float | None = None) -> bool:
        """Compatibility wrapper for the blocking ``*OPC?`` query."""
        return parse_int(self.operation_complete_raw(timeout_s=timeout_s)) == 1

    def operation_complete_raw(self, *, timeout_s: float | None = None) -> str:
        """Preserve the instrument reply for legacy callers."""
        return self._client.query("*OPC?", timeout_s=timeout_s)

    def wait_operation_complete(self, timeout_s: float) -> None:
        try:
            response = self.operation_complete_raw(timeout_s=timeout_s)
        except TransportTimeoutError as exc:
            raise OperationTimeoutError(f"operation did not complete within {timeout_s}s") from exc
        if parse_int(response) != 1:
            raise OperationTimeoutError(f"*OPC? reported {response!r} rather than completion")

    def set_operation_complete(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*OPC", timeout_s=timeout_s)

    def wait(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*WAI", timeout_s=timeout_s)

    def trigger(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*TRG", timeout_s=timeout_s)

    def self_test(self, *, timeout_s: float | None = None) -> SelfTestResult:
        raw = self._client.query("*TST?", timeout_s=timeout_s)
        return SelfTestResult(code=parse_int(raw), raw=raw)

    def read_status_byte(self, *, timeout_s: float | None = None) -> int:
        """Use serialized serial poll where exposed, otherwise fall back to ``*STB?``."""
        serial_poll = getattr(self._client.transport, "read_status_byte", None)
        if callable(serial_poll):
            with self._client.operation_lock():
                value = serial_poll(timeout_s=timeout_s)
            if type(value) is not int or not 0 <= value <= 255:
                raise TransportError(
                    f"serial poll returned invalid status byte {value!r}; expected integer 0..255"
                )
            return value
        return self.query_status_byte(timeout_s=timeout_s)

    def read_event_status(self, *, timeout_s: float | None = None) -> int:
        return self._query_byte_register("*ESR?", timeout_s=timeout_s)

    def _query_byte_register(self, command: str, *, timeout_s: float | None = None) -> int:
        raw = self._client.query(command, timeout_s=timeout_s)
        value = parse_int(raw)
        if not 0 <= value <= 255:
            raise ResponseParseError("expected unsigned 8-bit IEEE register", raw=raw)
        return value

    def query_status_byte(self, *, timeout_s: float | None = None) -> int:
        """Explicit *STB?; never substitute transport-level serial poll."""
        return self._query_byte_register("*STB?", timeout_s=timeout_s)

    def set_event_status_enable(self, mask: int, *, timeout_s: float | None = None) -> None:
        if type(mask) is not int or not 0 <= mask <= 255:
            raise ConfigurationError("event status enable mask must be an integer in 0..255")
        self._client.write(f"*ESE {mask}", timeout_s=timeout_s)

    def query_event_status_enable(self, *, timeout_s: float | None = None) -> int:
        return self._query_byte_register("*ESE?", timeout_s=timeout_s)

    def save(self, slot: int, *, timeout_s: float | None = None) -> None:
        """Model-specific slot ceiling belongs to the caller."""
        if type(slot) is not int or slot < 0:
            raise ConfigurationError("save slot must be a nonnegative integer")
        self._client.write(f"*SAV {slot}", timeout_s=timeout_s)

    def recall(self, slot: int, *, timeout_s: float | None = None) -> None:
        """Model-specific slot ceiling belongs to the caller."""
        if type(slot) is not int or slot < 0:
            raise ConfigurationError("recall slot must be a nonnegative integer")
        self._client.write(f"*RCL {slot}", timeout_s=timeout_s)
