"""The examples must keep working; a broken example is worse than none."""

from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

#: Needs an instrument on the other end, so it is checked for syntax only.
HARDWARE_ONLY = {"05_real_instruments.py"}


def runnable() -> list[Path]:
    return sorted(p for p in EXAMPLES.glob("*.py") if p.name not in HARDWARE_ONLY)


def test_there_are_runnable_examples() -> None:
    assert runnable()


@pytest.mark.parametrize("example", runnable(), ids=lambda p: p.name)
def test_example_runs(example: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runpy.run_path(str(example), run_name="__main__")
    assert capsys.readouterr().out.strip()


@pytest.mark.parametrize(
    "example", sorted(EXAMPLES / name for name in HARDWARE_ONLY), ids=lambda p: p.name
)
def test_hardware_example_is_at_least_valid(example: Path) -> None:
    compile(example.read_text(encoding="utf-8"), str(example), "exec")


def test_examples_run_as_scripts() -> None:
    """They are documented as `python examples/...`, so that must work too."""
    example = EXAMPLES / "01_typed_queries.py"
    result = subprocess.run(
        [sys.executable, str(example)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    assert "identity" in result.stdout
