"""Private helpers shared by the standard-library socket transports."""

from __future__ import annotations

import math
import socket
import time

from scpi_driver_core.exceptions import ConfigurationError, TransportError, TransportTimeoutError


def validate_timeout(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ConfigurationError(f"{name} must be finite and positive, got {value!r}")


def effective_timeout(override: float | None, default: float) -> float:
    if override is None:
        return default
    validate_timeout(override, "timeout_s")
    return override


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise TransportTimeoutError("socket operation exceeded its timeout")
    return value


def translate_socket_error(exc: OSError, action: str) -> TransportError:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return TransportTimeoutError(f"socket {action} timed out")
    return TransportError(f"socket {action} failed: {exc}")
