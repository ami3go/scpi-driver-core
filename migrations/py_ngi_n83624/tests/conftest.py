"""Redirect the RFDS-008 evidence engine's result root during tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _redirect_evidence_root(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    yield
