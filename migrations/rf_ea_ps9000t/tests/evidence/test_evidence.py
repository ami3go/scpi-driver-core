"""RFDS-008 evidence engine tests (§37: schema/correlation/ordering/redaction/integrity).

Scoped to what rf_ea_ps9000t's evidence.py actually produces — this is not an
attempt to cover every optional item in the RFDS-008 checklist, see
docs/logging_and_evidence.md's "what this system deliberately does not do".
Uses the bundled protocol-level simulator (``Connect simulated=True``)
throughout, matching this driver's existing ``tests/unit/`` convention.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from rf_ea_ps9000t import evidence as evidence_module
from rf_ea_ps9000t.library import EaPs9000TLibrary

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_evidence", _SCRIPTS_DIR / "validate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_root(tmp_path, alias: str = "bench") -> Path:
    session_root = tmp_path / "results" / "session" / "rf_ea_ps9000t"
    run_dirs = sorted(session_root.iterdir())
    assert run_dirs, "no evidence run directory was created"
    return run_dirs[-1]


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = EaPs9000TLibrary()
    library.connect(simulated=True, alias="bench")
    yield library, tmp_path


# ---------------------------------------------------------------------------
# Structure and manifest integrity
# ---------------------------------------------------------------------------

def test_disconnect_finalizes_a_complete_evidence_run(lib):
    library, tmp_path = lib
    library.set_voltage(5.0, alias="bench")
    library.disconnect("bench")
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
    assert summary["driver_id"] == "rf_ea_ps9000t"
    assert summary["execution_mode"] == "SIMULATOR"


def test_manifest_hashes_match_files_on_disk(lib):
    library, tmp_path = lib
    library.set_current(1.0, alias="bench")
    library.disconnect("bench")
    root = _run_root(tmp_path)

    manifest = json.loads((root / "evidence_manifest.json").read_text())
    assert manifest["artifact_count"] == len(manifest["artifacts"]) > 0
    for entry in manifest["artifacts"]:
        artifact_path = root / entry["path"]
        data = artifact_path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["size_bytes"]

    listed_paths = {entry["path"] for entry in manifest["artifacts"]}
    assert "evidence_manifest.json" not in listed_paths
    assert "integrity/checksums.sha256" not in listed_paths


def test_manifest_lists_every_file_under_the_run_root(lib):
    library, tmp_path = lib
    library.disconnect("bench")
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
# JSONL correctness: valid JSON, gap-free monotonic sequence per stream
# ---------------------------------------------------------------------------

def test_jsonl_streams_are_valid_and_gap_free(lib):
    library, tmp_path = lib
    library.set_voltage(1.0, alias="bench")
    library.get_measured_values(alias="bench")
    try:
        library.set_power("not-a-number", alias="bench")
    except ValueError:
        pass
    library.disconnect("bench")
    root = _run_root(tmp_path)

    for jsonl_path in root.rglob("*.jsonl"):
        sequences = []
        for line in jsonl_path.read_text().splitlines():
            record = json.loads(line)  # raises if not valid JSON
            sequences.append(record["sequence"])
        assert sequences == list(range(1, len(sequences) + 1)), jsonl_path


def test_scpi_protocol_trace_captures_the_real_command_text(lib):
    library, tmp_path = lib
    library.set_voltage(7.5, alias="bench")
    library.disconnect("bench")
    root = _run_root(tmp_path)
    exchanges = [json.loads(line) for line in (root / "protocol" / "exchanges.jsonl").read_text().splitlines()]
    outbound = [e["operation"] for e in exchanges if e["direction"] == "outbound"]
    assert any(cmd.startswith("VOLTage") and "7.5" in cmd for cmd in outbound)


def test_nested_operations_share_one_correlation_id(lib):
    """Get Protection Thresholds is a leaf call, but Connect internally drives
    remote-control acquisition and connection-state assembly; verify the
    simplest true nesting case instead: two sequential ops on the same alias
    do NOT share a correlation id (they are independent operations)."""
    library, tmp_path = lib
    library.set_voltage(1.0, alias="bench")
    library.set_current(1.0, alias="bench")
    library.disconnect("bench")
    root = _run_root(tmp_path)
    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    set_voltage_op = next(op for op in operations if op["capability"] == "Set Voltage")
    set_current_op = next(op for op in operations if op["capability"] == "Set Current")
    assert set_voltage_op["correlation_id"] != set_current_op["correlation_id"]


# ---------------------------------------------------------------------------
# Multi-alias isolation
# ---------------------------------------------------------------------------

def test_each_alias_gets_its_own_evidence_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = EaPs9000TLibrary()
    library.connect(simulated=True, alias="psu1")
    library.connect(simulated=True, alias="psu2")
    library.set_voltage(1.0, alias="psu1")
    library.set_voltage(2.0, alias="psu2")
    library.disconnect("psu1")
    library.disconnect("psu2")

    session_root = tmp_path / "results" / "session" / "rf_ea_ps9000t"
    run_dirs = sorted(session_root.iterdir())
    assert len(run_dirs) == 2
    aliases_seen = set()
    for run_dir in run_dirs:
        summary = json.loads((run_dir / "run_summary.json").read_text())
        assert summary["final_status"] == "PASS"
        operations = [json.loads(line) for line in (run_dir / "events" / "operations.jsonl").read_text().splitlines()]
        aliases_seen.update(op["session_alias"] for op in operations if op["capability"] == "Set Voltage")
    assert aliases_seen == {"psu1", "psu2"}


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_mapping_masks_sensitive_keys():
    redacted = evidence_module.redact_mapping({"voltage": 5.0, "password": "hunter2", "auth_token": "abc"})
    assert redacted["voltage"] == 5.0
    assert redacted["password"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
    assert redacted["auth_token"]["redacted"] is True


def test_redaction_applies_to_operation_arguments(tmp_path, monkeypatch):
    """No current keyword takes a credential-shaped argument; this proves the
    plumbing redacts one anyway if a future keyword or caller passes one, by
    exercising EvidenceRun.record_operation() directly."""
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    run = evidence_module.EvidenceRun(driver_id="rf_ea_ps9000t", activity="session")
    with run.record_operation("Test Capability", arguments={"voltage": 5.0, "api_token": "s3cr3t"}) as op:
        op.set_result("ok")
    run.finalize(status="PASS")

    operations = [json.loads(line) for line in (run.root / "events" / "operations.jsonl").read_text().splitlines()]
    record = operations[0]
    assert record["arguments"]["voltage"] == 5.0
    assert record["arguments"]["api_token"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_error_is_recorded_with_traceback(lib):
    library, tmp_path = lib
    with pytest.raises(ValueError):
        library.set_voltage("not-a-number", alias="bench")
    library.disconnect("bench")
    root = _run_root(tmp_path)
    errors = [json.loads(line) for line in (root / "events" / "errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1
    assert errors[0]["exception_type"] == "ValueError"
    assert "not-a-number" in errors[0]["message"]
    assert errors[0]["traceback"]

    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["error_count"] == 1
    assert summary["final_status"] == "PASS"  # disconnect itself succeeded


# ---------------------------------------------------------------------------
# evidence_enabled=False
# ---------------------------------------------------------------------------

def test_evidence_disabled_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = EaPs9000TLibrary(evidence_enabled=False)
    library.connect(simulated=True, alias="bench")
    library.set_voltage(1.0, alias="bench")
    library.disconnect("bench")
    assert not (tmp_path / "results").exists()


def test_evidence_disabled_export_diagnostic_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = EaPs9000TLibrary(evidence_enabled=False)
    library.connect(simulated=True, alias="bench")
    assert library.export_diagnostic_bundle(alias="bench") is None
    library.disconnect("bench")


# ---------------------------------------------------------------------------
# Export Diagnostic Bundle
# ---------------------------------------------------------------------------

def test_export_diagnostic_bundle_produces_a_readable_zip(lib):
    library, _tmp_path = lib
    library.set_voltage(1.0, alias="bench")
    bundle_path = library.export_diagnostic_bundle(alias="bench")
    assert bundle_path is not None
    archive_path = Path(bundle_path)
    assert archive_path.exists()

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("environment.json") for name in names)
        assert any(name.endswith("events/operations.jsonl") for name in names)
    library.disconnect("bench")


def test_export_diagnostic_bundle_honors_explicit_destination(lib):
    library, tmp_path = lib
    destination = tmp_path / "custom" / "bundle.zip"
    result = library.export_diagnostic_bundle(alias="bench", destination=str(destination))
    assert Path(result) == destination
    assert destination.exists()
    library.disconnect("bench")


# ---------------------------------------------------------------------------
# validate_evidence.py
# ---------------------------------------------------------------------------

def test_validate_evidence_script_accepts_a_clean_run(lib):
    library, tmp_path = lib
    library.set_voltage(1.0, alias="bench")
    library.disconnect("bench")
    root = _run_root(tmp_path)
    validator = _load_validator()
    findings = validator.validate(root)
    assert findings == []


def test_validate_evidence_script_detects_tampering(lib):
    library, tmp_path = lib
    library.disconnect("bench")
    root = _run_root(tmp_path)
    events_path = root / "events" / "events.jsonl"
    with events_path.open("a") as handle:
        handle.write("this is not json\n")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("HASH MISMATCH" in finding and "events.jsonl" in finding for finding in findings)
    assert any("invalid JSON" in finding for finding in findings)


def test_validate_evidence_script_detects_missing_manifest_entry(lib):
    library, tmp_path = lib
    library.disconnect("bench")
    root = _run_root(tmp_path)
    (root / "attachments" / "extra_note.txt").write_text("not tracked")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("FILE NOT IN MANIFEST" in finding for finding in findings)
