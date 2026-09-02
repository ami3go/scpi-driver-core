from __future__ import annotations

import scpi_driver_core
from scpi_driver_core import exceptions


def test_package_imports() -> None:
    assert scpi_driver_core.__version__ == "0.1.0.dev0"


def test_error_hierarchy_is_reachable_from_the_top_level() -> None:
    assert scpi_driver_core.ScpiDriverError is exceptions.ScpiDriverError


def test_top_level_exports_the_whole_error_hierarchy() -> None:
    assert set(scpi_driver_core.__all__) == set(exceptions.__all__)


def test_every_exported_name_is_present() -> None:
    for name in scpi_driver_core.__all__:
        assert hasattr(scpi_driver_core, name), name
