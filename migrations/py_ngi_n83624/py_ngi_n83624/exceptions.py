"""Exception hierarchy for the NGI N83624 driver."""

from __future__ import annotations


class N83624Error(Exception):
    """Base class for all NGI N83624 driver errors."""


class CommunicationError(N83624Error):
    """Raised when the transport layer cannot communicate with the instrument."""


class TimeoutError(CommunicationError):
    """Raised when a transport operation times out."""


class ProtocolError(N83624Error):
    """Raised when the instrument returns malformed or unexpected data."""


class CommandError(ProtocolError):
    """Raised for SCPI command errors reported by the device."""


class ExecutionError(ProtocolError):
    """Raised for SCPI execution errors reported by the device."""


class ValidationError(N83624Error):
    """Raised before a command is sent when user input is invalid."""


class SafetyError(N83624Error):
    """Raised when a requested operation violates the configured safety policy."""


class DeviceError(N83624Error):
    """Raised when the device reports a fault state or refuses expected behavior."""


class SessionStateError(N83624Error):
    """Raised when an operation is invalid in the current session state."""


class InterlockError(SafetyError):
    """Raised when an external bench interlock blocks an operation."""


class HeartbeatError(CommunicationError):
    """Raised when heartbeat supervision fails."""


class RecoveryError(CommunicationError):
    """Raised when reconnect or session recovery fails."""


class BusyError(N83624Error):
    """Raised when an operation cannot proceed because another operation is active."""


COMMAND_ERROR_MESSAGES: dict[int, str] = {
    -100: "Command error",
    -101: "Invalid character",
    -102: "Syntax error",
    -103: "Invalid separator",
    -104: "Data type error",
    -105: "GET not allowed",
    -108: "Parameter not allowed",
    -109: "Missing parameter",
    -112: "Program mnemonic too long",
    -113: "Undefined header",
    -115: "Command cannot query",
    -120: "Numeric data error",
    -121: "Invalid character in number",
    -123: "Exponent too large",
    -124: "Too many digits",
    -128: "Numeric data not allowed",
    -130: "Suffix error",
    -131: "Invalid suffix",
    -134: "Suffix too long",
    -138: "Suffix not allowed",
    -140: "Character data error",
    -141: "Invalid character data",
    -144: "Character data too long",
    -148: "Character data not allowed",
    -150: "String data error",
    -151: "Invalid string data",
    -158: "String data not allowed",
    -160: "Block data error",
    -168: "Block data not allowed",
    -170: "Expression error",
    -178: "Expression data not allowed",
    -180: "Macro error",
}

EXECUTION_ERROR_MESSAGES: dict[int, str] = {
    -200: "Execution error",
    -201: "Invalid while in local",
    -203: "Command protected",
    -211: "Trigger ignored",
    -213: "Init ignored",
    -220: "Parameter error",
    -221: "Settings conflict",
    -222: "Data out of range",
    -223: "Too much data",
    -224: "Illegal parameter value",
    -225: "Out of memory",
    -230: "Data corrupt or stale",
    -241: "Hardware missing",
    -250: "Mass storage error",
    -256: "File name not found",
    -257: "File name error",
    -258: "Media protected",
    -260: "Expression error",
    -270: "Macro error",
    -280: "Program error",
    -290: "Memory use error",
    -291: "Out of memory",
    -292: "Referenced name does not exist",
    -293: "Referenced name already exists",
    -294: "Incompatible type",
    -296: "Operation not allowed",
}


def exception_for_error_code(code: int, message: str | None = None) -> N83624Error:
    """Return a typed exception instance for a vendor SCPI error code."""
    detail = message or COMMAND_ERROR_MESSAGES.get(code) or EXECUTION_ERROR_MESSAGES.get(code) or "Unknown device error"
    if -199 <= code <= -100:
        return CommandError(f"SCPI command error {code}: {detail}")
    if -299 <= code <= -200:
        return ExecutionError(f"SCPI execution error {code}: {detail}")
    return DeviceError(f"Device error {code}: {detail}")
