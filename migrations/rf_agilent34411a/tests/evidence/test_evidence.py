"""RFDS-008 evidence engine tests (§37: schema/correlation/ordering/redaction/integrity).

Scoped to what rf_agilent34411a's evidence.py actually produces — see
rf_phidget_relay/docs/logging_and_evidence.md's "what this system
deliberately does not do" for the same scope decisions applied here.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from rf_agilent34411a import evidence as evidence_module
from rf_agilent34411a.library import Agilent34411ALibrary

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_evidence", _SCRIPTS_DIR / "validate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_root(tmp_path) -> Path:
    session_root = tmp_path / "results" / "session" / "rf_agilent34411a"
    run_dirs = sorted(session_root.iterdir())
    assert run_dirs, "no evidence run directory was created"
    return run_dirs[-1]


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    obj = Agilent34411ALibrary()
    obj.connect(alias="A", simulated=True)
    yield obj, tmp_path


# ---------------------------------------------------------------------------
# Structure and manifest integrity
# ---------------------------------------------------------------------------

def test_end_suite_finalizes_a_complete_evidence_run(lib):
    obj, tmp_path = lib
    obj.set_function("VOLT", alias="A")
    obj.get_immediate_measurement(alias="A")
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)

    for expected in (
        "run_summary.json",
        "run_summary.md",
        "environment.json",
        "device_identity.json",
        "evidence_manifest.json",
        "events/events.jsonl",
        "events/operations.jsonl",
        "protocol/exchanges.jsonl",
        "protocol/outbound_trace.log",
        "protocol/inbound_trace.log",
        "integrity/checksums.sha256",
    ):
        assert (root / expected).exists(), f"missing {expected}"

    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["schema"] == "rfds.run_summary"
    assert summary["final_status"] == "PASS"
    assert summary["driver_id"] == "rf_agilent34411a"
    assert summary["execution_mode"] == "SIMULATOR"


def test_manifest_hashes_match_files_on_disk(lib):
    obj, tmp_path = lib
    obj.get_identity(alias="A")
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)

    manifest = json.loads((root / "evidence_manifest.json").read_text())
    assert manifest["artifact_count"] == len(manifest["artifacts"]) > 0
    for entry in manifest["artifacts"]:
        data = (root / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["size_bytes"]
    listed_paths = {entry["path"] for entry in manifest["artifacts"]}
    assert "evidence_manifest.json" not in listed_paths
    assert "integrity/checksums.sha256" not in listed_paths


def test_manifest_lists_every_file_under_the_run_root(lib):
    obj, tmp_path = lib
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)
    manifest = json.loads((root / "evidence_manifest.json").read_text())
    listed = {entry["path"] for entry in manifest["artifacts"]}
    on_disk = {
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*")
        if p.is_file() and p.name not in ("evidence_manifest.json", "checksums.sha256")
    }
    assert listed == on_disk


# ---------------------------------------------------------------------------
# Multi-alias behavior
# ---------------------------------------------------------------------------

def test_multiple_aliases_share_one_run_with_per_alias_identity(lib):
    obj, tmp_path = lib
    obj.connect(alias="B", simulated=True)
    obj.get_identity(alias="A")
    obj.get_identity(alias="B")
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)

    identity = json.loads((root / "device_identity.json").read_text())
    assert set(identity["sessions"]) == {"A", "B"}

    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    aliases_seen = {op["session_alias"] for op in operations if op["capability"] == "Get Identity"}
    assert aliases_seen == {"A", "B"}


def test_mixed_simulator_and_real_alias_reports_mixed_execution_mode(lib, monkeypatch):
    """No real hardware in this environment: force the 'real' alias down the
    simulated code path but with execution_mode manually overridden to prove
    the MIXED-detection logic in Connect, independent of actual VISA I/O."""
    obj, _tmp_path = lib  # alias "A" already connected as SIMULATOR
    run = obj._evidence
    assert run.execution_mode == "SIMULATOR"
    run.execution_mode = "REAL_HARDWARE"  # simulate as if A had been real hardware
    obj.connect(alias="B", simulated=True)
    assert obj._evidence.execution_mode == "MIXED"


# ---------------------------------------------------------------------------
# JSONL correctness: valid JSON, gap-free monotonic sequence per stream
# ---------------------------------------------------------------------------

def test_jsonl_streams_are_valid_and_gap_free(lib):
    obj, tmp_path = lib
    obj.set_function("VOLT", alias="A")
    obj.get_immediate_measurement(alias="A")
    with pytest.raises(ValueError):
        obj.set_range("NOT_A_FUNCTION", 1, alias="A")
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)

    for jsonl_path in root.rglob("*.jsonl"):
        sequences = []
        for line in jsonl_path.read_text().splitlines():
            record = json.loads(line)
            sequences.append(record["sequence"])
        assert sequences == list(range(1, len(sequences) + 1)), jsonl_path


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_mapping_masks_sensitive_keys():
    redacted = evidence_module.redact_mapping({"function": "VOLT", "password": "hunter2", "auth_token": "abc"})
    assert redacted["function"] == "VOLT"
    assert redacted["password"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
    assert redacted["auth_token"]["redacted"] is True


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_error_is_recorded_with_category(lib):
    obj, tmp_path = lib
    with pytest.raises(ValueError):
        obj.set_range("NOT_A_FUNCTION", 1, alias="A")
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)
    errors = [json.loads(line) for line in (root / "events" / "errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1
    assert errors[0]["session_alias"] == "A"
    assert errors[0]["category"] in {"VALIDATION", "UNKNOWN"}

    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["error_count"] == 1
    assert summary["final_status"] == "PASS"  # _end_suite itself succeeded


# ---------------------------------------------------------------------------
# NullEvidenceRun / evidence_enabled=False
# ---------------------------------------------------------------------------

def test_evidence_disabled_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    obj = Agilent34411ALibrary(evidence_enabled=False)
    obj.connect(alias="A", simulated=True)
    obj.get_immediate_measurement(alias="A")
    obj._end_suite("dummy", {})
    assert not (tmp_path / "results").exists()


def test_evidence_disabled_export_diagnostic_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    obj = Agilent34411ALibrary(evidence_enabled=False)
    obj.connect(alias="A", simulated=True)
    assert obj.export_diagnostic_bundle() is None


# ---------------------------------------------------------------------------
# Export Diagnostic Bundle
# ---------------------------------------------------------------------------

def test_export_diagnostic_bundle_produces_a_readable_zip(lib):
    obj, _tmp_path = lib
    obj.get_immediate_measurement(alias="A")
    bundle_path = obj.export_diagnostic_bundle()
    assert bundle_path is not None
    archive_path = Path(bundle_path)
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("environment.json") for name in names)
        assert any(name.endswith("events/operations.jsonl") for name in names)
    obj._end_suite("dummy", {})


def test_export_diagnostic_bundle_honors_explicit_destination(lib):
    obj, tmp_path = lib
    destination = tmp_path / "custom" / "bundle.zip"
    result = obj.export_diagnostic_bundle(str(destination))
    assert Path(result) == destination
    assert destination.exists()
    obj._end_suite("dummy", {})


# ---------------------------------------------------------------------------
# validate_evidence.py
# ---------------------------------------------------------------------------

def test_validate_evidence_script_accepts_a_clean_run(lib):
    obj, tmp_path = lib
    obj.get_immediate_measurement(alias="A")
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)
    validator = _load_validator()
    assert validator.validate(root) == []


def test_validate_evidence_script_detects_tampering(lib):
    obj, tmp_path = lib
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)
    with (root / "events" / "events.jsonl").open("a") as handle:
        handle.write("this is not json\n")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("HASH MISMATCH" in finding and "events.jsonl" in finding for finding in findings)
    assert any("invalid JSON" in finding for finding in findings)


def test_validate_evidence_script_detects_missing_manifest_entry(lib):
    obj, tmp_path = lib
    obj._end_suite("dummy", {})
    root = _run_root(tmp_path)
    (root / "attachments" / "extra_note.txt").write_text("not tracked")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("FILE NOT IN MANIFEST" in finding for finding in findings)
