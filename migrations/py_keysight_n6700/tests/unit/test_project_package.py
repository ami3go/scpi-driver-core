from __future__ import annotations

import subprocess
import sys


def test_ai_contracts_are_current() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/generate_ai_contract.py", "--check"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_project_package_standard() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/verify_project_package.py",
            "--source",
            ".",
            "--expected-release",
            "26.09",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
