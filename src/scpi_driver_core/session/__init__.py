"""Named sessions, their health, and the registry that holds them."""

from scpi_driver_core.session.health import SessionHealth
from scpi_driver_core.session.registry import (
    DEFAULT_ALIAS,
    SessionRegistry,
    normalize_alias,
)
from scpi_driver_core.session.session import DEFAULT_HEALTH_QUERY, ScpiSession

__all__ = [
    "DEFAULT_ALIAS",
    "DEFAULT_HEALTH_QUERY",
    "ScpiSession",
    "SessionHealth",
    "SessionRegistry",
    "normalize_alias",
]
