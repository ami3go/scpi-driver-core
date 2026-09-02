from __future__ import annotations

import scpi_driver_core


def test_package_imports() -> None:
    assert scpi_driver_core.__version__ == "0.1.0.dev0"
