"""SCPI text framing, parsing, and client layer."""

from scpi_driver_core.scpi.client import ScpiClient
from scpi_driver_core.scpi.codec import ScpiTextCodec
from scpi_driver_core.scpi.engineering import (
    SI_PREFIXES,
    SUPPORTED_UNITS,
    EngineeringValue,
    parse_engineering_value,
)
from scpi_driver_core.scpi.ieee488 import Ieee4882
from scpi_driver_core.scpi.parsers import (
    parse_bool,
    parse_csv,
    parse_float,
    parse_identity,
    parse_int,
    parse_optional_unit_float,
    parse_scpi_error,
    quote_scpi_string,
)

__all__ = [
    "SI_PREFIXES",
    "SUPPORTED_UNITS",
    "EngineeringValue",
    "Ieee4882",
    "ScpiClient",
    "ScpiTextCodec",
    "parse_bool",
    "parse_csv",
    "parse_engineering_value",
    "parse_float",
    "parse_identity",
    "parse_int",
    "parse_optional_unit_float",
    "parse_scpi_error",
    "quote_scpi_string",
]
