from __future__ import annotations

import scpi_driver_core
from scpi_driver_core import exceptions


def test_package_imports() -> None:
    assert scpi_driver_core.__version__ == "0.1.0.dev2"


def test_error_hierarchy_is_reachable_from_the_top_level() -> None:
    assert scpi_driver_core.ScpiDriverError is exceptions.ScpiDriverError


def test_top_level_exports_the_whole_error_hierarchy() -> None:
    assert set(exceptions.__all__) <= set(scpi_driver_core.__all__)


def test_top_level_exports_scpi_client() -> None:
    assert scpi_driver_core.ScpiClient.__name__ == "ScpiClient"


def test_every_exported_name_is_present() -> None:
    for name in scpi_driver_core.__all__:
        assert hasattr(scpi_driver_core, name), name


def test_documented_scpi_import_surface_is_shallow() -> None:
    """The task doc promises these from scpi_driver_core.scpi directly."""
    from scpi_driver_core.scpi import (  # noqa: F401
        Ieee4882,
        encode_definite_length_block,
        parse_bool,
        parse_float,
    )


def test_documented_transport_import_surface_is_shallow() -> None:
    from scpi_driver_core.transport import (  # noqa: F401
        MockTransport,
        SerialTransport,
        TcpTransport,
        Transport,
        UdpTransport,
        VisaTransport,
    )
