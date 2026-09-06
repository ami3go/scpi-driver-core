"""Shared pytest fixtures for rf_agilent33220a.

Redirects the RFDS-008 evidence engine's result root into a per-test
temporary directory so running the test suite never writes ``results/``
into the repository itself.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _redirect_evidence_root(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    yield
