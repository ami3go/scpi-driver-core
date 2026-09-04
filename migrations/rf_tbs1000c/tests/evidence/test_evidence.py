"""RFDS-008 evidence engine tests (§37: schema/correlation/ordering/redaction/integrity).

Scoped to what rf_tbs1000c's evidence.py actually produces — see
rf_phidget_relay/docs/logging_and_evidence.md's "what this system
deliberately does not do" for the fuller rationale (this engine was adapted
from that one).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from rf_tbs1000c import evidence as evidence_module
from rf_tbs1000c.library import Tbs1000cLibrary
from tbs1000c.exceptions import Tbs1000cValidationError

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_evidence", _SCRIPTS_DIR / "validate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_root(tmp_path) -> Path:
    session_root = tmp_path / "results" / "session" / "rf_tbs1000c"
    run_dirs = sorted(session_root.iterdir())
    assert run_dirs, "no evidence run directory was created"
    return run_dirs[-1]


@pytest.fixture
def scope(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = Tbs1000cLibrary()
    lib.connect(simulated=True)
    yield lib, tmp_path
    # Idempotent: a test that already called _end_suite (or never connected)
    # must not raise here.
    lib._end_suite(None, {})


# ---------------------------------------------------------------------------
# Structure and manifest integrity
# ---------------------------------------------------------------------------

def test_end_suite_finalizes_a_complete_evidence_run(scope):
    lib, tmp_path = scope
    lib.set_channel_scale(1, 0.5)
    lib._end_suite(None, {})
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
        "integrity/checksums.sha256",
    ):
        assert (root / expected).exists(), f"missing {expected}"

    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["schema"] == "rfds.run_summary"
    assert summary["final_status"] == "PASS"
    assert summary["driver_id"] == "rf_tbs1000c"
    assert summary["execution_mode"] == "SIMULATOR"


def test_manifest_hashes_match_files_on_disk(scope):
    lib, tmp_path = scope
    lib.set_channel_scale(1, 0.2)
    lib._end_suite(None, {})
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


def test_manifest_lists_every_file_under_the_run_root(scope):
    lib, tmp_path = scope
    lib._end_suite(None, {})
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
# JSONL correctness
# ---------------------------------------------------------------------------

def test_jsonl_streams_are_valid_and_gap_free(scope):
    lib, tmp_path = scope
    lib.set_channel_scale(1, 0.5)
    lib.get_channel_scale(1)
    try:
        lib.set_channel_scale(99, 0.5)
    except Tbs1000cValidationError:
        pass
    lib._end_suite(None, {})
    root = _run_root(tmp_path)

    for jsonl_path in root.rglob("*.jsonl"):
        sequences = [json.loads(line)["sequence"] for line in jsonl_path.read_text().splitlines()]
        assert sequences == list(range(1, len(sequences) + 1)), jsonl_path


def test_scpi_commands_are_traced(scope):
    lib, tmp_path = scope
    lib.set_channel_scale(1, 0.5)
    lib._end_suite(None, {})
    root = _run_root(tmp_path)
    exchanges = [json.loads(line) for line in (root / "protocol" / "exchanges.jsonl").read_text().splitlines()]
    outbound_ops = [e["operation"] for e in exchanges if e["direction"] == "outbound"]
    assert any("SCAle" in op for op in outbound_ops)


# ---------------------------------------------------------------------------
# Execution mode / simulation honesty
# ---------------------------------------------------------------------------

def test_execution_mode_mixed_when_run_spans_real_and_simulated(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = Tbs1000cLibrary()
    lib.connect(simulated=True, alias="sim")
    run = lib._ensure_evidence()
    # A real USBTMC connection can't be exercised in this test environment,
    # so simulate the second Connect's effect on execution_mode directly —
    # note_execution_mode() is exactly what a real Connect call would invoke.
    run.note_execution_mode("REAL_HARDWARE")
    lib._end_suite(None, {})
    root = _run_root(tmp_path)
    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["execution_mode"] == "MIXED"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_mapping_masks_sensitive_keys():
    redacted = evidence_module.redact_mapping({"channel": 1, "password": "hunter2", "auth_token": "abc"})
    assert redacted["channel"] == 1
    assert redacted["password"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
    assert redacted["auth_token"]["redacted"] is True


def test_redaction_applies_to_operation_arguments(tmp_path, monkeypatch):
    """No current keyword takes a credential-shaped argument; this proves the
    plumbing redacts one anyway, by exercising EvidenceRun.record_operation()
    directly."""
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    run = evidence_module.EvidenceRun(driver_id="rf_tbs1000c", activity="session")
    with run.record_operation("Test Capability", arguments={"channel": 1, "api_token": "s3cr3t"}) as op:
        op.set_result("ok")
    run.finalize(status="PASS")
    operations = [json.loads(line) for line in (run.root / "events" / "operations.jsonl").read_text().splitlines()]
    record = operations[0]
    assert record["arguments"]["channel"] == 1
    assert record["arguments"]["api_token"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_error_is_recorded_with_category(scope):
    lib, tmp_path = scope
    with pytest.raises(Tbs1000cValidationError):
        lib.set_channel_scale(99, 0.5)
    lib._end_suite(None, {})
    root = _run_root(tmp_path)
    errors = [json.loads(line) for line in (root / "events" / "errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1
    assert errors[0]["category"] == "VALIDATION"
    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["error_count"] == 1
    assert summary["final_status"] == "PASS"  # the suite-end cleanup itself succeeded


# ---------------------------------------------------------------------------
# NullEvidenceRun / evidence_enabled=False
# ---------------------------------------------------------------------------

def test_evidence_disabled_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = Tbs1000cLibrary(evidence_enabled=False)
    lib.connect(simulated=True)
    lib.set_channel_scale(1, 0.5)
    lib._end_suite(None, {})
    assert not (tmp_path / "results").exists()


def test_evidence_disabled_export_diagnostic_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = Tbs1000cLibrary(evidence_enabled=False)
    lib.connect(simulated=True)
    assert lib.export_diagnostic_bundle() is None
    lib._end_suite(None, {})


# ---------------------------------------------------------------------------
# Export Diagnostic Bundle
# ---------------------------------------------------------------------------

def test_export_diagnostic_bundle_produces_a_readable_zip(scope):
    lib, _tmp_path = scope
    lib.set_channel_scale(1, 0.5)
    bundle_path = lib.export_diagnostic_bundle()
    assert bundle_path is not None
    archive_path = Path(bundle_path)
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("environment.json") for name in names)
        assert any(name.endswith("events/operations.jsonl") for name in names)


def test_export_diagnostic_bundle_honors_explicit_destination(scope):
    lib, tmp_path = scope
    destination = tmp_path / "custom" / "bundle.zip"
    result = lib.export_diagnostic_bundle(str(destination))
    assert Path(result) == destination
    assert destination.exists()


# ---------------------------------------------------------------------------
# validate_evidence.py
# ---------------------------------------------------------------------------

def test_validate_evidence_script_accepts_a_clean_run(scope):
    lib, tmp_path = scope
    lib.set_channel_scale(1, 0.5)
    lib._end_suite(None, {})
    root = _run_root(tmp_path)
    validator = _load_validator()
    assert validator.validate(root) == []


def test_validate_evidence_script_detects_tampering(scope):
    lib, tmp_path = scope
    lib._end_suite(None, {})
    root = _run_root(tmp_path)
    events_path = root / "events" / "events.jsonl"
    with events_path.open("a") as handle:
        handle.write("this is not json\n")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("HASH MISMATCH" in finding and "events.jsonl" in finding for finding in findings)
    assert any("invalid JSON" in finding for finding in findings)
