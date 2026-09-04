"""RFDS-008 evidence engine tests (§37: schema/correlation/ordering/redaction/integrity).

Scoped to what rf_ngi_n83624's evidence.py actually produces — see
docs/logging-and-evidence.md's "what this system deliberately does not do".
Uses the driver's own built-in ``SimpleN83624Emulator`` (via ``Open N83624
Emulator``) rather than a bespoke fake, so these tests also exercise the real
``protocol_observer`` wiring through ``ngi_n83624.driver``.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
from ngi_n83624.exceptions import ValidationError

from rf_ngi_n83624 import NGI_N83624
from rf_ngi_n83624 import evidence as evidence_module

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_evidence", _SCRIPTS_DIR / "validate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_root(tmp_path: Path) -> Path:
    session_root = tmp_path / "results" / "session" / "rf_ngi_n83624"
    run_dirs = sorted(session_root.iterdir())
    assert run_dirs, "no evidence run directory was created"
    return run_dirs[-1]


def _run_roots(tmp_path: Path) -> list[Path]:
    session_root = tmp_path / "results" / "session" / "rf_ngi_n83624"
    return sorted(session_root.iterdir())


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = NGI_N83624(auto_close_on_suite_end=False)
    lib.open_n83624_emulator(alias="emu", max_voltage_v=5.0, max_current_ma=500)
    yield lib, tmp_path
    with contextlib.suppress(Exception):
        lib.close_all_n83624_connections()


# ---------------------------------------------------------------------------
# Structure and manifest integrity
# ---------------------------------------------------------------------------

def test_close_finalizes_a_complete_evidence_run(library):
    lib, tmp_path = library
    lib.identify_n83624()
    lib.close_n83624_connection("emu")
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
    assert summary["driver_id"] == "rf_ngi_n83624"
    assert summary["execution_mode"] == "SIMULATOR"  # Open N83624 Emulator


def test_manifest_hashes_match_files_on_disk(library):
    lib, tmp_path = library
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)

    manifest = json.loads((root / "evidence_manifest.json").read_text())
    assert manifest["artifact_count"] == len(manifest["artifacts"])
    assert manifest["artifact_count"] > 0
    for entry in manifest["artifacts"]:
        data = (root / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["size_bytes"]

    listed_paths = {entry["path"] for entry in manifest["artifacts"]}
    assert "evidence_manifest.json" not in listed_paths
    assert "integrity/checksums.sha256" not in listed_paths


def test_manifest_lists_every_file_under_the_run_root(library):
    lib, tmp_path = library
    lib.close_n83624_connection("emu")
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
# Multi-session behavior specific to this driver's GLOBAL-scope, multi-alias design
# ---------------------------------------------------------------------------

def test_each_alias_gets_its_own_run_directory(library):
    lib, tmp_path = library
    lib.open_n83624_emulator(alias="emu2", max_voltage_v=5.0, max_current_ma=500)
    lib.close_all_n83624_connections()
    roots = _run_roots(tmp_path)
    assert len(roots) == 2


def test_close_all_finalizes_the_outer_operation_record_too(library):
    """Regression test: Close All N83624 Connections calling Close N83624
    Connection internally (per alias) must not finalize (and hash-freeze) the
    run before the outer call's own operation record is written to it."""
    lib, tmp_path = library
    lib.close_all_n83624_connections()
    root = _run_root(tmp_path)
    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    capabilities = [op["capability"] for op in operations]
    assert "Close N83624 Connection" in capabilities
    assert "Close All N83624 Connections" in capabilities
    # If this were finalized too early, the outer operation's record would be
    # missing from operations.jsonl even though the manifest already hashed it.
    validator = _load_validator()
    assert validator.validate(root) == []


def test_closing_one_alias_does_not_finalize_another(library):
    lib, tmp_path = library
    lib.open_n83624_emulator(alias="emu2", max_voltage_v=5.0, max_current_ma=500)
    lib.close_n83624_connection("emu")
    roots = _run_roots(tmp_path)
    finalized = [r for r in roots if (r / "run_summary.json").exists()]
    open_still = [r for r in roots if not (r / "run_summary.json").exists()]
    assert len(finalized) == 1
    assert len(open_still) == 1


def test_suite_end_finalizes_a_run_whose_alias_never_had_a_session(tmp_path, monkeypatch):
    """Regression: a keyword called before any Open creates an evidence run for
    the resolved alias, but _finalize_closed_sessions only finalizes aliases
    that *lost* a session. Such a run was left on disk with environment.json and
    events/ but no run_summary.json, evidence_manifest.json or checksums."""
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = NGI_N83624(auto_close_on_suite_end=False)

    lib.close_all_n83624_connections()  # no session was ever opened
    lib._end_suite("Suite", {})

    root = _run_root(tmp_path)
    for expected in (
        "run_summary.json",
        "evidence_manifest.json",
        "integrity/checksums.sha256",
    ):
        assert (root / expected).exists(), f"missing {expected}"
    assert _load_validator().validate(root) == []


def test_suite_end_derives_fail_status_from_recorded_errors(tmp_path, monkeypatch):
    """Regression: _finalize_remaining_evidence_runs defaulted to status="PASS"
    for every remaining run, so an alias whose only operation failed was still
    summarised as PASS with error_count 1. Each alias is judged on its own
    record."""
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = NGI_N83624(auto_close_on_suite_end=False)

    with contextlib.suppress(Exception):
        lib.open_n83624_tcp_connection(
            "bench", host="10.255.255.1", port=7000, timeout=0.2
        )
    lib._end_suite("Suite", {})

    summaries = [
        json.loads((root / "run_summary.json").read_text())
        for root in _run_roots(tmp_path)
        if (root / "run_summary.json").exists()
    ]
    assert summaries, "no finalized run was written"
    failed = [s for s in summaries if s["error_count"] > 0]
    assert failed, "expected the unreachable-host run to record an error"
    for summary in failed:
        assert summary["final_status"] == "FAIL"
    for summary in summaries:
        if summary["error_count"] == 0:
            assert summary["final_status"] == "PASS"


def test_suite_end_finalizes_evidence_even_when_auto_close_is_disabled(tmp_path, monkeypatch):
    """auto_close_on_suite_end governs closing connections, never whether the
    evidence record is left complete."""
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = NGI_N83624(auto_close_on_suite_end=False)
    lib.open_n83624_emulator(alias="emu", max_voltage_v=5.0, max_current_ma=500)
    lib.identify_n83624(alias="emu")

    lib._end_suite("Suite", {})  # session deliberately left open

    root = _run_root(tmp_path)
    assert (root / "run_summary.json").exists()
    assert _load_validator().validate(root) == []


# ---------------------------------------------------------------------------
# JSONL correctness: valid JSON, gap-free monotonic sequence per stream
# ---------------------------------------------------------------------------

def test_jsonl_streams_are_valid_and_gap_free(library):
    lib, tmp_path = library
    lib.measure_channel(1)
    with contextlib.suppress(Exception):
        lib.measure_channel_voltage(99)  # invalid channel
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)

    for jsonl_path in root.rglob("*.jsonl"):
        sequences = []
        for line in jsonl_path.read_text().splitlines():
            record = json.loads(line)
            sequences.append(record["sequence"])
        assert sequences == list(range(1, len(sequences) + 1)), jsonl_path


def test_nested_operations_share_one_correlation_id(library):
    """Close All N83624 Connections calls Close N83624 Connection internally;
    both should correlate under the outer call's ID."""
    lib, tmp_path = library
    lib.close_all_n83624_connections()
    root = _run_root(tmp_path)
    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    outer = next(op for op in operations if op["capability"] == "Close All N83624 Connections")
    inner = next(op for op in operations if op["capability"] == "Close N83624 Connection")
    assert outer["correlation_id"] == inner["correlation_id"]
    assert outer["operation_id"] != inner["operation_id"]


# ---------------------------------------------------------------------------
# Protocol tracing through ngi_n83624.driver.protocol_observer
# ---------------------------------------------------------------------------

def test_protocol_trace_captures_real_scpi_traffic(library):
    lib, tmp_path = library
    lib.identify_n83624()
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)
    outbound = (root / "protocol" / "outbound_trace.log").read_text()
    inbound = (root / "protocol" / "inbound_trace.log").read_text()
    assert "*IDN?" in outbound
    assert "NGI,N83624" in inbound


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_mapping_masks_sensitive_keys():
    redacted = evidence_module.redact_mapping({"channel": 5, "password": "hunter2", "auth_token": "abc"})
    assert redacted["channel"] == 5
    assert redacted["password"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
    assert redacted["auth_token"]["redacted"] is True


def test_redaction_applies_to_operation_arguments(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    run = evidence_module.EvidenceRun(driver_id="rf_ngi_n83624", activity="session")
    with run.record_operation("Test Capability", arguments={"channel": 5, "api_token": "s3cr3t"}) as op:
        op.set_result("ok")
    run.finalize(status="PASS")
    operations = [json.loads(line) for line in (run.root / "events" / "operations.jsonl").read_text().splitlines()]
    record = operations[0]
    assert record["arguments"]["channel"] == 5
    assert record["arguments"]["api_token"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_error_is_recorded_with_correct_category(library):
    lib, tmp_path = library
    with pytest.raises(ValidationError):
        lib.measure_channel_voltage(99)
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)
    errors = [json.loads(line) for line in (root / "events" / "errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1
    assert errors[0]["category"] == "VALIDATION"
    assert errors[0]["exception_type"] == "ValidationError"


# ---------------------------------------------------------------------------
# NullEvidenceRun / evidence_enabled=False
# ---------------------------------------------------------------------------

def test_evidence_disabled_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = NGI_N83624(auto_close_on_suite_end=False, evidence_enabled=False)
    lib.open_n83624_emulator(alias="emu", max_voltage_v=5.0, max_current_ma=500)
    lib.identify_n83624()
    lib.close_n83624_connection("emu")
    assert not (tmp_path / "results").exists()


def test_evidence_disabled_export_diagnostic_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    lib = NGI_N83624(auto_close_on_suite_end=False, evidence_enabled=False)
    lib.open_n83624_emulator(alias="emu", max_voltage_v=5.0, max_current_ma=500)
    assert lib.export_diagnostic_bundle(alias="emu") is None
    lib.close_n83624_connection("emu")


# ---------------------------------------------------------------------------
# Export Diagnostic Bundle
# ---------------------------------------------------------------------------

def test_export_diagnostic_bundle_produces_a_readable_zip(library):
    lib, _tmp_path = library
    lib.identify_n83624()
    bundle_path = lib.export_diagnostic_bundle(alias="emu")
    assert bundle_path is not None
    archive_path = Path(bundle_path)
    assert archive_path.exists()
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("environment.json") for name in names)
        assert any(name.endswith("events/operations.jsonl") for name in names)


def test_export_diagnostic_bundle_honors_explicit_destination(library):
    lib, tmp_path = library
    destination = tmp_path / "custom" / "bundle.zip"
    result = lib.export_diagnostic_bundle(alias="emu", destination=str(destination))
    assert Path(result) == destination
    assert destination.exists()


# ---------------------------------------------------------------------------
# validate_evidence.py
# ---------------------------------------------------------------------------

def test_validate_evidence_script_accepts_a_clean_run(library):
    lib, tmp_path = library
    lib.identify_n83624()
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)
    validator = _load_validator()
    assert validator.validate(root) == []


def test_validate_evidence_script_detects_tampering(library):
    lib, tmp_path = library
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)
    events_path = root / "events" / "events.jsonl"
    with events_path.open("a") as handle:
        handle.write("this is not json\n")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("HASH MISMATCH" in finding and "events.jsonl" in finding for finding in findings)
    assert any("invalid JSON" in finding for finding in findings)


def test_validate_evidence_script_detects_missing_manifest_entry(library):
    lib, tmp_path = library
    lib.close_n83624_connection("emu")
    root = _run_root(tmp_path)
    (root / "attachments" / "extra_note.txt").write_text("not tracked")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("FILE NOT IN MANIFEST" in finding for finding in findings)
