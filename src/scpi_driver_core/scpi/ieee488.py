"""IEEE-488.2 common commands and optional IEEE-488.1 transport capabilities."""

from __future__ import annotations

from scpi_driver_core.exceptions import OperationTimeoutError, TransportTimeoutError
from scpi_driver_core.models import Identity, SelfTestResult
from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.scpi.parsers import parse_identity, parse_int
from scpi_driver_core.transport.base import SupportsSerialPoll

__all__ = ["Ieee4882"]


class Ieee4882:
    def __init__(self, client: ScpiClient) -> None:
        self._client = client

    @property
    def client(self) -> ScpiClient:
        return self._client

    def identify(self, *, timeout_s: float | None = None) -> Identity:
        return parse_identity(self._client.query("*IDN?", timeout_s=timeout_s))

    def clear_status(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*CLS", timeout_s=timeout_s)

    def reset(self, *, timeout_s: float | None = None) -> None:
        self._client.write("*RST", timeout_s=timeout_s)

    def operation_complete(self, *, timeout_s: float | None = None) -> bool:
        """Compatibility wrapper for the blocking ``*OPC?`` query.

        ``*OPC?`` blocks until completion and conforming devices answer 1, so
        callers should normally prefer :meth:`wait_operation_complete`.
        """
        return parse_int(self._client.query("*OPC?", timeout_s=timeout_s)) == 1

    def wait_operation_complete(self, timeout_s: float) -> None:
        try:
            response = self._client.query("*OPC?", timeout_s=timeout_s)
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
        """Use serial poll where the transport supports it, otherwise ``*STB?``."""
        transport = self._client.transport
        if isinstance(transport, SupportsSerialPoll):
            return transport.read_status_byte(timeout_s=timeout_s)
        return parse_int(self._client.query("*STB?", timeout_s=timeout_s))

    def read_event_status(self, *, timeout_s: float | None = None) -> int:
        return parse_int(self._client.query("*ESR?", timeout_s=timeout_s))
