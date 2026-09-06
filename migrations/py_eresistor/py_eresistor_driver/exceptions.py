"""Custom exceptions for the E-Resistor driver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


class EResistorError(Exception):
    """Base exception for all driver errors."""


class ConnectionError(EResistorError):
    """Transport connection failed or was lost."""


class ScpiError(EResistorError):
    """SCPI command failed or returned an error response."""

    def __init__(
        self,
        message: str,
        *,
        command: str | None = None,
        response: str | None = None,
        code: int | None = None,
        host: str | None = None,
        channel: int | None = None,
    ) -> None:
        super().__init__(message)
        self.command = command
        self.response = response
        self.code = code
        self.host = host
        self.channel = channel


class HttpApiError(EResistorError):
    """HTTP helper API failed."""


class DeviceNotFoundError(EResistorError):
    """No matching E-Resistor board was found."""


class CalibrationError(EResistorError):
    """Calibration data is missing, invalid, or stale."""


class ResistanceSolveError(EResistorError):
    """Requested resistance could not be solved within the configured policy."""


class TemperatureTableError(EResistorError):
    """Temperature-to-resistance table is invalid or unavailable."""


class SimulationError(EResistorError):
    """Curve simulation failed."""


class SafetyLimitError(EResistorError):
    """A requested operation violates configured safety limits."""


class TimeoutError(ConnectionError):
    """An operation timed out."""


@dataclass(frozen=True)
class ParsedScpiError:
    code: Optional[int]
    message: str


def parse_scpi_error(response: str) -> ParsedScpiError | None:
    """Parse firmware error lines like ERR,-113,"Undefined header"."""
    text = response.strip()
    if not text.upper().startswith("ERR"):
        return None
    parts = text.split(",", 2)
    code: int | None = None
    msg = text
    if len(parts) >= 2:
        try:
            code = int(parts[1].strip())
        except ValueError:
            code = None
    if len(parts) == 3:
        msg = parts[2].strip().strip('"')
    return ParsedScpiError(code=code, message=msg)
