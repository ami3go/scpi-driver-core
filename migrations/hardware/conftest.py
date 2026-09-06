"""Local pytest configuration for the hardware sweep.

Self-contained so this directory can be run on its own, and so the ``hardware``
marker and the ``--hardware`` flag exist without touching the core's pytest
configuration. The root suite sets ``testpaths = ["tests"]``, so nothing here
is collected by a plain ``pytest`` at the repository root.
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="run the sweep against a real instrument (see migrations/hardware/README.md)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "hardware: needs a physical instrument")
