"""Regression tests for RFDS-003 shared-core packaging requirements."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from rf_hp34401a.plugin import Hp34401APluginProvider


PACKAGE_ROOT = Path(__file__).resolve().parents[2]


def test_rfds_core_is_a_runtime_dependency() -> None:
    """RFDS-003 requires rfds-core in the main project dependency set."""
    text = (PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project_section = text.split("[project.optional-dependencies]", 1)[0]
    assert re.search(r'["\']rfds-core>=1\.0,<2\.0["\']', project_section)


def test_plugin_environment_treats_missing_rfds_core_as_required(monkeypatch) -> None:
    """Plugin discovery must not report a conformant environment without rfds-core."""
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name: None if name == "rfds_core" else object(),
    )

    result = Hp34401APluginProvider.validate_environment()
    check = next(item for item in result["checks"] if item["id"] == "rfds-core")

    assert check["required"] is True
    assert check["status"] == "FAIL"
    assert check["requirement"] == ">=1.0,<2.0"
    assert result["status"] == "FAIL"
