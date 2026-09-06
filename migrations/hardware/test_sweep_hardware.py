"""The gated sweep, as a pytest run. Never executed against hardware yet.

Collect it and it skips: the gates are unmet in any checked-out copy of this
repository, because every shipped allowlist is unsigned. That is the intended
resting state. See ``README.md`` for what signing means before you change it.

This file is deliberately thin. Everything that can be decided without an
instrument lives in :mod:`sweep` and is covered by ``test_gates.py``; what is
left here is the part that cannot be tested without hardware, so there is as
little of it as possible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from connectors import CONNECTORS, connect  # noqa: E402
from sweep import gate_failures, load_allowlist, resource_variable, run_sweep  # noqa: E402

ALLOWLISTS = Path(__file__).resolve().parent / "allowlists"
TRANSCRIPTS = Path(__file__).resolve().parent / "transcripts"


@pytest.mark.hardware
@pytest.mark.parametrize("driver", sorted(p.stem for p in ALLOWLISTS.glob("py_*.toml")))
def test_read_only_sweep(driver: str, request: pytest.FixtureRequest) -> None:
    """Call every signed-off read-only method once, on a real instrument."""
    if not request.config.getoption("--hardware"):
        pytest.skip("hardware tests need --hardware")

    allowlist_path = ALLOWLISTS / f"{driver}.toml"
    blocked = gate_failures(driver=driver, allowlist_path=allowlist_path)
    if blocked:
        pytest.skip(f"{driver} gates not met: " + "; ".join(blocked))

    if CONNECTORS.get(driver) is None:
        pytest.skip(
            f"{driver} has no single-call constructor; sweep it from your own "
            f"script by passing a connected driver to run_sweep()"
        )

    import os

    resource = os.environ[resource_variable(driver)]
    expected = os.environ.get(f"SCPI_HARDWARE_{driver.upper()}_IDENTITY", "")
    if not expected:
        pytest.skip(
            f"SCPI_HARDWARE_{driver.upper()}_IDENTITY is not set; the sweep will "
            f"not run without knowing which instrument it expects"
        )

    instance = connect(driver, resource)
    try:
        report = run_sweep(
            driver=driver,
            instance=instance,
            allowlist=load_allowlist(allowlist_path),
            identity=lambda: str(instance.identify()),
            expected_identity=expected,
            still_connected=lambda: bool(getattr(instance, "connected", True)),
            transcript=TRANSCRIPTS / f"{driver}.jsonl",
        )
    finally:
        close = getattr(instance, "close", None)
        if callable(close):
            close()

    assert not report.failures, (
        f"{len(report.failures)} of {len(report.results)} methods failed: "
        + ", ".join(f"{f.name} ({f.error})" for f in report.failures)
    )
    assert report.aborted_after is None, f"link lost after {report.aborted_after}"
