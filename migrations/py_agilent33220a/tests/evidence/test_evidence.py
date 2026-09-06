"""RFDS-008 evidence engine tests (§37: schema/correlation/ordering/redaction/integrity).

Scoped to what rf_agilent33220a's evidence.py actually produces — see
docs/logging_and_evidence.md's "what this system deliberately does not do".
Uses the bundled simulator (``simulated=True``) rather than a fake factory,
since this driver has a real simulator and unit tests already lean on it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

from rf_agilent33220a import evidence as evidence_module
from rf_agilent33220a.library import Agilent33220ALibrary

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_evidence", _SCRIPTS_DIR / "validate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_root(tmp_path) -> Path:
    session_root = tmp_path / "results" / "session" / "rf_agilent33220a"
    run_dirs = sorted(session_root.iterdir())
    assert run_dirs, "no evidence run directory was created"
    return run_dirs[-1]


@pytest.fixture
def lib(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = Agilent33220ALibrary()
    library.connect(simulated=True)
    yield library, tmp_path
    # Suite-scoped library: emulate the RF end-suite hook to finalize evidence.
    library._end_suite("test", {})


# ---------------------------------------------------------------------------
# Structure and manifest integrity
# ---------------------------------------------------------------------------

def test_end_suite_finalizes_a_complete_evidence_run(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = Agilent33220ALibrary()
    library.connect(simulated=True)
    library.set_frequency(1000.0)
    library._end_suite("test", {})

    root = _run_root(tmp_path)
    for expected in (
        "run_summary.json", "run_summary.md", "environment.json", "device_identity.json",
        "evidence_manifest.json", "events/events.jsonl", "events/operations.jsonl",
        "protocol/exchanges.jsonl", "protocol/outbound_trace.log", "integrity/checksums.sha256",
    ):
        assert (root / expected).exists(), f"missing {expected}"

    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["schema"] == "rfds.run_summary"
    assert summary["final_status"] == "PASS"
    assert summary["driver_id"] == "rf_agilent33220a"
    assert summary["execution_mode"] == "SIMULATOR"


def test_manifest_hashes_match_files_on_disk(lib):
    library, tmp_path = lib
    library.set_amplitude(1.0)
    library._end_suite("test", {})
    root = _run_root(tmp_path)

    manifest = json.loads((root / "evidence_manifest.json").read_text())
    assert manifest["artifact_count"] == len(manifest["artifacts"]) > 0
    for entry in manifest["artifacts"]:
        data = (root / entry["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["size_bytes"]
    listed = {entry["path"] for entry in manifest["artifacts"]}
    assert "evidence_manifest.json" not in listed
    assert "integrity/checksums.sha256" not in listed


def test_manifest_lists_every_file_under_the_run_root(lib):
    library, tmp_path = lib
    library._end_suite("test", {})
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
# JSONL correctness, protocol tracing, correlation
# ---------------------------------------------------------------------------

def test_jsonl_streams_are_valid_and_gap_free(lib):
    library, tmp_path = lib
    library.set_frequency(2000.0)
    library.get_frequency()
    try:
        library.set_gpib_address(999)  # invalid, out of range
    except Exception:
        pass
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    for jsonl_path in root.rglob("*.jsonl"):
        sequences = [json.loads(line)["sequence"] for line in jsonl_path.read_text().splitlines()]
        assert sequences == list(range(1, len(sequences) + 1)), jsonl_path


def test_scpi_commands_are_traced(lib):
    library, tmp_path = lib
    library.set_frequency(12345.0)
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    outbound = (root / "protocol" / "outbound_trace.log").read_text()
    assert "FREQuency 12345.0" in outbound


def test_operation_and_protocol_share_correlation(lib):
    library, tmp_path = lib
    library.set_frequency(5000.0)
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    exchanges = [json.loads(line) for line in (root / "protocol" / "exchanges.jsonl").read_text().splitlines()]
    set_freq_op = next(op for op in operations if op["capability"] == "Set Frequency")
    matching_exchanges = [ex for ex in exchanges if ex["operation_id"] == set_freq_op["operation_id"]]
    assert matching_exchanges, "no protocol exchange was correlated to the Set Frequency operation"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_mapping_masks_sensitive_keys():
    redacted = evidence_module.redact_mapping({"frequency": 1000, "security_code": "1234", "new_code": "5678"})
    assert redacted["frequency"] == 1000
    assert redacted["security_code"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
    assert redacted["new_code"]["redacted"] is True


def test_calibration_security_code_argument_is_redacted(lib):
    library, tmp_path = lib
    library.enable_calibration_mode("ENABLE CALIBRATION")
    library.unlock_calibration("AT33220A")  # simulator's default factory security code
    library.set_calibration_security_code("SECRET1234")
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    operations = (root / "events" / "operations.jsonl").read_text()
    assert "SECRET1234" not in operations
    assert '"redacted": true' in operations


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

def test_error_is_recorded_with_category(lib):
    library, tmp_path = lib
    with pytest.raises(Exception):
        library.set_frequency(-1.0)  # invalid frequency
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    errors = [json.loads(line) for line in (root / "events" / "errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1
    assert errors[0]["category"] in ("VALIDATION", "HARDWARE")
    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["error_count"] == 1


# ---------------------------------------------------------------------------
# NullEvidenceRun / evidence_enabled=False
# ---------------------------------------------------------------------------

def test_evidence_disabled_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = Agilent33220ALibrary(evidence_enabled=False)
    library.connect(simulated=True)
    library.set_frequency(1000.0)
    library._end_suite("test", {})
    assert not (tmp_path / "results").exists()


def test_evidence_disabled_export_diagnostic_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = Agilent33220ALibrary(evidence_enabled=False)
    library.connect(simulated=True)
    assert library.export_diagnostic_bundle() is None
    library._end_suite("test", {})


# ---------------------------------------------------------------------------
# Export Diagnostic Bundle
# ---------------------------------------------------------------------------

def test_export_diagnostic_bundle_produces_a_readable_zip(lib):
    library, tmp_path = lib
    library.set_frequency(3000.0)
    bundle_path = library.export_diagnostic_bundle()
    assert bundle_path is not None
    with zipfile.ZipFile(Path(bundle_path)) as archive:
        names = archive.namelist()
        assert any(name.endswith("environment.json") for name in names)
        assert any(name.endswith("protocol/outbound_trace.log") for name in names)


def test_export_diagnostic_bundle_honors_explicit_destination(lib):
    library, tmp_path = lib
    destination = tmp_path / "custom" / "bundle.zip"
    result = library.export_diagnostic_bundle(str(destination))
    assert Path(result) == destination
    assert destination.exists()


# ---------------------------------------------------------------------------
# Multi-alias correlation
# ---------------------------------------------------------------------------

def test_multiple_aliases_record_distinct_session_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    library = Agilent33220ALibrary()
    library.connect(alias="gen1", simulated=True)
    library.connect(alias="gen2", simulated=True)
    library.set_frequency(1000.0, alias="gen1")
    library.set_frequency(2000.0, alias="gen2")
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    aliases = {op["session_alias"] for op in operations if op["capability"] == "Set Frequency"}
    assert aliases == {"gen1", "gen2"}


# ---------------------------------------------------------------------------
# validate_evidence.py
# ---------------------------------------------------------------------------

def test_validate_evidence_script_accepts_a_clean_run(lib):
    library, tmp_path = lib
    library.set_frequency(1000.0)
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    findings = _load_validator().validate(root)
    assert findings == []


def test_validate_evidence_script_detects_tampering(lib):
    library, tmp_path = lib
    library._end_suite("test", {})
    root = _run_root(tmp_path)
    with (root / "events" / "events.jsonl").open("a") as handle:
        handle.write("not json\n")
    findings = _load_validator().validate(root)
    assert any("HASH MISMATCH" in finding for finding in findings)
    assert any("invalid JSON" in finding for finding in findings)
