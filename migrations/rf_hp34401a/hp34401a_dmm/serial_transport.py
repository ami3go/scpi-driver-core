"""RS-232 transport using pyserial (spec section 21.2).

``pyserial`` is imported lazily inside ``_do_open`` so the package imports and the
CLI ``--help`` work without pyserial installed and without hardware.
"""

from __future__ import annotations

import logging

from .config import SerialRs232Config
from .enums import TransportType
from .errors import InstrumentConnectionError, InstrumentTimeoutError, TransportError
from .transports import BaseTransport

_log = logging.getLogger("hp34401a_dmm.transport")

# RS-232 device-clear character for the 34401A (spec section 21.1).
CTRL_C = "\x03"

_PARITY_MAP = {"none": "N", "even": "E", "odd": "O"}


class SerialRs232Transport(BaseTransport):
    _transport_type = TransportType.SERIAL_RS232

    def __init__(self, config: SerialRs232Config, *, raw_traffic_log: bool = False) -> None:
        super().__init__(
            read_termination=config.read_termination,
            write_termination=config.write_termination,
            encoding=config.encoding,
            raw_traffic_log=raw_traffic_log,
        )
        self.config = config
        self._serial = None  # set on open

    @property
    def name(self) -> str:
        return f"serial:{self.config.port}@{self.config.baudrate}"

    def _do_open(self) -> None:
        try:
            import serial  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise InstrumentConnectionError(
                "pyserial is required for RS-232 transport; install with "
                "'pip install pyserial>=3.5' or the 'serial' extra."
            ) from exc

        parity_const = {
            "N": serial.PARITY_NONE,
            "E": serial.PARITY_EVEN,
            "O": serial.PARITY_ODD,
        }[_PARITY_MAP[self.config.parity]]

        try:
            self._serial = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                bytesize=self.config.data_bits,
                parity=parity_const,
                stopbits=serial.STOPBITS_TWO,
                timeout=self.config.timeout_s,
                write_timeout=self.config.write_timeout_s,
                dsrdtr=self.config.use_dtr_dsr,
                rtscts=False,
            )
            # Flush any stale local buffers (spec section 13.1 step 2).
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except Exception as exc:  # serial.SerialException and friends
            if self._serial is not None:
                try:
                    self._serial.close()
                finally:
                    self._serial = None
            raise InstrumentConnectionError(
                f"Could not open serial port {self.config.port!r}: {exc}"
            ) from exc

    def _do_close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def _send(self, data: str) -> None:
        if self._serial is None:
            raise TransportError("Serial port is not open")
        try:
            self._serial.write(data.encode(self._encoding))
        except Exception as exc:
            cls = (
                InstrumentTimeoutError
                if "timeout" in type(exc).__name__.lower()
                else TransportError
            )
            raise cls(f"Serial write failed on {self.name}: {exc}") from exc

    def _recv(self) -> str:
        if self._serial is None:
            raise TransportError("Serial port is not open")
        try:
            raw = self._serial.read_until(self._read_termination.encode(self._encoding))
        except Exception as exc:
            raise TransportError(f"Serial read failed on {self.name}: {exc}") from exc
        if not raw:
            raise InstrumentTimeoutError(
                f"Serial read timed out after {self.config.timeout_s}s on {self.name}"
            )
        terminator = self._read_termination.encode(self._encoding)
        if terminator and not raw.endswith(terminator):
            # pyserial.read_until() may return partial bytes on timeout. Treat
            # that as a timeout/protocol failure; accepting a numeric-looking
            # partial response would be a wrong-data risk in production.
            preview = raw.decode(self._encoding, errors="replace")
            raise InstrumentTimeoutError(
                f"Serial read timed out with partial response on {self.name}: {preview!r}"
            )
        return raw.decode(self._encoding, errors="replace")

    def _clear(self) -> None:
        """RS-232 device clear: send Ctrl-C and flush buffers (spec 21.1/21.2)."""
        if self._serial is None:
            return
        try:
            self._serial.write(CTRL_C.encode(self._encoding))
            self._serial.reset_input_buffer()
            self._serial.reset_output_buffer()
        except Exception as exc:  # pragma: no cover - hardware dependent
            raise TransportError(f"Serial clear failed on {self.name}: {exc}") from exc

    def _set_timeout(self, timeout_s: float) -> None:
        if self._serial is not None:
            self._serial.timeout = timeout_s
