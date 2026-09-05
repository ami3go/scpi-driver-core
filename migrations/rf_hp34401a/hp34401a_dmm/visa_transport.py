"""VISA GPIB transport, built on ``scpi-driver-core`` (spec section 21.3, R9/R10).

PyVISA is loaded by the core and only when the session is opened, so the
package imports and the CLI ``--help`` still work without pyvisa installed and
without hardware.

The GPIB address rules in :func:`validate_gpib_resource` stay here: talk-only
mode and primary-address ranges are GPIB semantics, not generic transport
concerns, and the core has no business knowing about them.
"""

from __future__ import annotations

import logging
import re

from .config import VisaGpibConfig
from .enums import (
    MAX_GPIB_ADDRESS,
    MIN_GPIB_ADDRESS,
    TALK_ONLY_GPIB_ADDRESS,
    TransportType,
)
from scpi_driver_core import ScpiClient
from scpi_driver_core.exceptions import (
    ConfigurationError,
    ScpiDriverError,
    TransportTimeoutError,
)
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import FlushDirection, VisaTransport

from .errors import InstrumentConnectionError, InstrumentTimeoutError, TransportError
from .transports import BaseTransport

_log = logging.getLogger("hp34401a_dmm.transport")

_GPIB_ADDR_RE = re.compile(r"GPIB\d*::(\d+)", re.IGNORECASE)


def validate_gpib_resource(resource: str) -> None:
    """R10: reject talk-only (31) and out-of-range GPIB primary addresses."""
    m = _GPIB_ADDR_RE.search(resource)
    if not m:
        return  # non-GPIB resource string; nothing to validate here
    addr = int(m.group(1))
    if addr == TALK_ONLY_GPIB_ADDRESS:
        raise InstrumentConnectionError(
            f"GPIB address {addr} selects talk-only mode and cannot be queried. "
            f"Use a primary address in {MIN_GPIB_ADDRESS}-{MAX_GPIB_ADDRESS}."
        )
    if not (MIN_GPIB_ADDRESS <= addr <= MAX_GPIB_ADDRESS):
        raise InstrumentConnectionError(
            f"GPIB primary address {addr} is out of range "
            f"({MIN_GPIB_ADDRESS}-{MAX_GPIB_ADDRESS})."
        )


class VisaGpibTransport(BaseTransport):
    _transport_type = TransportType.VISA_GPIB

    def __init__(self, config: VisaGpibConfig, *, raw_traffic_log: bool = False) -> None:
        super().__init__(
            read_termination=config.read_termination,
            write_termination=config.write_termination,
            raw_traffic_log=raw_traffic_log,
        )
        validate_gpib_resource(config.resource)  # R10, fail before opening
        self.config = config
        self._client: ScpiClient | None = None

    @property
    def name(self) -> str:
        """A human-readable name for this connection."""
        return f"visa:{self.config.resource}"

    def _do_open(self) -> None:
        codec = ScpiTextCodec(
            command_terminator=self.config.write_termination.encode("ascii"),
            response_terminator=self.config.read_termination.encode("ascii") or None,
        )
        try:
            transport = VisaTransport(
                self.config.resource,
                timeout_s=self.config.timeout_s,
                visa_library=self.config.visa_library or "",
            )
            transport.open()
        except ConfigurationError as exc:
            # Covers a missing PyVISA, which R9 wants reported with guidance.
            raise InstrumentConnectionError(
                "pyvisa is required for GPIB transport; install with "
                "'pip install pyvisa>=1.14'. GPIB additionally needs a vendor/native "
                "VISA backend (NI-VISA or Keysight IO Libraries); pyvisa-py alone "
                f"does not drive GPIB (R9). Underlying error: {exc}"
            ) from exc
        except ScpiDriverError as exc:
            raise InstrumentConnectionError(
                f"Could not open VISA resource {self.config.resource!r}: {exc}"
            ) from exc
        self._client = ScpiClient(transport, codec=codec, timeout_s=self.config.timeout_s)

    def _do_close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            client.transport.close()

    def _send(self, data: str) -> None:
        """``data`` already carries the write terminator from :class:`BaseTransport`.

        PyVISA's own terminations are disabled by the core, so unlike the
        pre-migration code this does not have to strip the terminator back off
        and hope PyVISA re-appends the same one.
        """
        client = self._require_client()
        try:
            client.write_bytes(data.encode("ascii"))
        except ScpiDriverError as exc:
            raise self._map_core_error(exc, "write") from exc

    def _recv(self) -> str:
        client = self._require_client()
        try:
            raw = client.read_bytes(client.response_request)
            return client.codec.decode_response(raw)
        except ScpiDriverError as exc:
            raise self._map_core_error(exc, "read") from exc

    def _clear(self) -> None:
        if self._client is not None:
            try:
                self._client.transport.flush(FlushDirection.BOTH)
            except ScpiDriverError as exc:  # pragma: no cover - hardware dependent
                raise TransportError(f"VISA clear failed on {self.name}: {exc}") from exc

    def _set_timeout(self, timeout_s: float) -> None:
        if self._client is not None:
            self._client.set_timeout(timeout_s)

    def _require_client(self) -> ScpiClient:
        if self._client is None:
            raise TransportError("VISA resource is not open")
        return self._client

    @staticmethod
    def _map_core_error(exc: ScpiDriverError, op: str) -> Exception:
        if isinstance(exc, TransportTimeoutError):
            return InstrumentTimeoutError(f"VISA {op} timed out: {exc}")
        return TransportError(f"VISA {op} failed: {exc}")
