"""RFDS-008 evidence engine tests (§37: schema/correlation/ordering/redaction/integrity).

Scoped to what rf_eresistor's evidence.py actually produces — this is not an
attempt to cover every optional item in the RFDS-008 checklist, see
docs/logging_and_evidence.md's "what this system deliberately does not do".

Since EResistorLibrary.connect() has no injectable client factory (unlike
rf_phidget_relay's output_factory), these tests monkeypatch
rf_eresistor.library.EResistorClient itself with a fake so the full
connect() path (protocol tracing wrap, device-identity capture) is exercised
exactly as Robot Framework would call it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest
import rf_eresistor.library as library_module
from rf_eresistor.library import EResistorLibrary

from rf_eresistor import evidence as evidence_module

_SCRIPTS_DIR = Path(__file__).parents[2] / "scripts"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_evidence", _SCRIPTS_DIR / "validate_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get_text(self, path):
        self.calls.append(path)
        if path == "/ping":
            return "pong"
        return "ok"


class FakeClient:
    def __init__(self, host="192.168.0.55", scpi_port=5025, http_port=80,
                 timeout=2.0, retries=2, audit_log_file=None):
        from eresistor_driver.models import ConnectionState, ShutdownPolicy

        self.host = host
        self.scpi_port = scpi_port
        self.http_port = http_port
        self.connection_state = ConnectionState.CONNECTED
        self.shutdown_policy = ShutdownPolicy.ALL_OFF
        self.http = FakeHttp()
        self.closed = False

    def safe_connect(self, all_off_on_connect=False):
        pass

    def idn(self):
        return "OpenBench,E-Resistor,SN001,0.4.0"

    def ping(self):
        # Mirrors EResistorClient.ping() -> EResistorHttpApi.ping() -> get_text("/ping"),
        # so this exercises the same traced boundary the real client would.
        return self.http.get_text("/ping").strip().lower() == "pong"

    def query(self, command, multiline_until=None):
        if command == "FAIL:ME":
            from eresistor_driver.exceptions import ScpiError

            raise ScpiError("simulated device error")
        return "OK"

    def get_serial(self):
        return "SN001"

    def get_firmware_version(self):
        return "0.4.0"

    def close(self):
        self.closed = True


def _run_root(tmp_path) -> Path:
    session_root = tmp_path / "results" / "session" / "rf_eresistor"
    run_dirs = sorted(session_root.iterdir())
    assert run_dirs, "no evidence run directory was created"
    return run_dirs[-1]


@pytest.fixture
def connected_lib(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    monkeypatch.setattr(library_module, "EResistorClient", FakeClient)
    lib = EResistorLibrary(host="192.168.0.55")
    lib.connect()
    yield lib, tmp_path


# ---------------------------------------------------------------------------
# Structure, manifest integrity, device identity
# ---------------------------------------------------------------------------

def test_disconnect_finalizes_a_complete_evidence_run(connected_lib):
    lib, tmp_path = connected_lib
    lib.ping()
    lib.disconnect()
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
    assert summary["driver_id"] == "rf_eresistor"
    assert summary["execution_mode"] == "REAL_HARDWARE"

    identity = json.loads((root / "device_identity.json").read_text())
    assert identity["identity"] == "OpenBench,E-Resistor,SN001,0.4.0"
    assert identity["serial"] == "SN001"
    assert identity["firmware_version"] == "0.4.0"


def test_manifest_hashes_match_files_on_disk(connected_lib):
    lib, tmp_path = connected_lib
    lib.disconnect()
    root = _run_root(tmp_path)

    manifest = json.loads((root / "evidence_manifest.json").read_text())
    assert manifest["artifact_count"] == len(manifest["artifacts"])
    assert manifest["artifact_count"] > 0
    for entry in manifest["artifacts"]:
        artifact_path = root / entry["path"]
        data = artifact_path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert len(data) == entry["size_bytes"]

    listed_paths = {entry["path"] for entry in manifest["artifacts"]}
    assert "evidence_manifest.json" not in listed_paths
    assert "integrity/checksums.sha256" not in listed_paths


def test_manifest_lists_every_file_under_the_run_root(connected_lib):
    lib, tmp_path = connected_lib
    lib.disconnect()
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
# Protocol tracing: SCPI (query) and HTTP (ping) both captured
# ---------------------------------------------------------------------------

def test_scpi_and_http_exchanges_are_both_traced(connected_lib):
    lib, tmp_path = connected_lib
    lib.ping()  # HTTP: client.http.get_text("/ping")
    lib.query("SYST:ERR?")  # SCPI: client.query(...)
    lib.disconnect()
    root = _run_root(tmp_path)

    exchanges = [json.loads(line) for line in (root / "protocol" / "exchanges.jsonl").read_text().splitlines()]
    transports = {exchange["transport"] for exchange in exchanges}
    assert "scpi_tcp" in transports
    assert "http" in transports
    directions = {exchange["direction"] for exchange in exchanges}
    assert directions == {"outbound", "inbound"}


# ---------------------------------------------------------------------------
# JSONL correctness: valid JSON, gap-free monotonic sequence per stream
# ---------------------------------------------------------------------------

def test_jsonl_streams_are_valid_and_gap_free(connected_lib):
    lib, tmp_path = connected_lib
    from eresistor_driver.exceptions import ScpiError

    lib.ping()
    lib.get_identity()
    try:
        lib.query("FAIL:ME")
    except ScpiError:
        pass
    lib.disconnect()
    root = _run_root(tmp_path)

    for jsonl_path in root.rglob("*.jsonl"):
        sequences = []
        for line in jsonl_path.read_text().splitlines():
            record = json.loads(line)  # raises if not valid JSON
            sequences.append(record["sequence"])
        assert sequences == list(range(1, len(sequences) + 1)), jsonl_path


def test_nested_operations_share_one_correlation_id(connected_lib):
    """Generic Disconnect calls the same decorated Disconnect From EResistor
    method internally; both operation records should correlate."""
    lib, tmp_path = connected_lib
    lib.generic_disconnect()
    root = _run_root(tmp_path)
    operations = [json.loads(line) for line in (root / "events" / "operations.jsonl").read_text().splitlines()]
    outer = next(op for op in operations if op["capability"] == "Disconnect")
    inner = next(op for op in operations if op["capability"] == "Disconnect From EResistor")
    assert outer["correlation_id"] == inner["correlation_id"]
    assert outer["operation_id"] != inner["operation_id"]


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

def test_redact_mapping_masks_sensitive_keys():
    redacted = evidence_module.redact_mapping({"channel": 5, "password": "hunter2", "auth_token": "abc"})
    assert redacted["channel"] == 5
    assert redacted["password"] == {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
    assert redacted["auth_token"]["redacted"] is True


def test_redaction_applies_to_operation_arguments(tmp_path, monkeypatch):
    """No current keyword takes a credential-shaped argument; this proves the
    plumbing redacts one anyway, by exercising EvidenceRun.record_operation()
    directly."""
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    run = evidence_module.EvidenceRun(driver_id="rf_eresistor", activity="session")
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

def test_error_is_recorded_with_traceback_and_category(connected_lib):
    from eresistor_driver.exceptions import ScpiError

    lib, tmp_path = connected_lib
    with pytest.raises(ScpiError):
        lib.query("FAIL:ME")
    lib.disconnect()
    root = _run_root(tmp_path)
    errors = [json.loads(line) for line in (root / "events" / "errors.jsonl").read_text().splitlines()]
    assert len(errors) == 1
    assert errors[0]["category"] == "HARDWARE"
    assert "simulated device error" in errors[0]["message"]
    assert "Traceback" in errors[0]["traceback"]

    summary = json.loads((root / "run_summary.json").read_text())
    assert summary["error_count"] == 1
    assert summary["final_status"] == "PASS"  # disconnect itself succeeded


# ---------------------------------------------------------------------------
# NullEvidenceRun / evidence_enabled=False
# ---------------------------------------------------------------------------

def test_evidence_disabled_writes_nothing_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    monkeypatch.setattr(library_module, "EResistorClient", FakeClient)
    lib = EResistorLibrary(host="192.168.0.55", evidence_enabled=False)
    lib.connect()
    lib.ping()
    lib.disconnect()
    assert not (tmp_path / "results").exists()


def test_evidence_disabled_export_diagnostic_bundle_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("RFDS_EVIDENCE_ROOT", str(tmp_path / "results"))
    monkeypatch.setattr(library_module, "EResistorClient", FakeClient)
    lib = EResistorLibrary(host="192.168.0.55", evidence_enabled=False)
    lib.connect()
    assert lib.export_diagnostic_bundle() is None
    lib.disconnect()


# ---------------------------------------------------------------------------
# Export Diagnostic Bundle
# ---------------------------------------------------------------------------

def test_export_diagnostic_bundle_produces_a_readable_zip(connected_lib):
    lib, _tmp_path = connected_lib
    lib.ping()
    bundle_path = lib.export_diagnostic_bundle()
    assert bundle_path is not None
    archive_path = Path(bundle_path)
    assert archive_path.exists()

    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert any(name.endswith("environment.json") for name in names)
        assert any(name.endswith("events/operations.jsonl") for name in names)
    lib.disconnect()


def test_export_diagnostic_bundle_honors_explicit_destination(connected_lib):
    lib, tmp_path = connected_lib
    destination = tmp_path / "custom" / "bundle.zip"
    result = lib.export_diagnostic_bundle(str(destination))
    assert Path(result) == destination
    assert destination.exists()
    lib.disconnect()


# ---------------------------------------------------------------------------
# validate_evidence.py
# ---------------------------------------------------------------------------

def test_validate_evidence_script_accepts_a_clean_run(connected_lib):
    lib, tmp_path = connected_lib
    lib.ping()
    lib.disconnect()
    root = _run_root(tmp_path)
    validator = _load_validator()
    findings = validator.validate(root)
    assert findings == []


def test_validate_evidence_script_detects_tampering(connected_lib):
    lib, tmp_path = connected_lib
    lib.disconnect()
    root = _run_root(tmp_path)
    events_path = root / "events" / "events.jsonl"
    with events_path.open("a") as handle:
        handle.write("this is not json\n")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("HASH MISMATCH" in finding and "events.jsonl" in finding for finding in findings)
    assert any("invalid JSON" in finding for finding in findings)


def test_validate_evidence_script_detects_missing_manifest_entry(connected_lib):
    lib, tmp_path = connected_lib
    lib.disconnect()
    root = _run_root(tmp_path)
    (root / "attachments" / "extra_note.txt").write_text("not tracked")
    validator = _load_validator()
    findings = validator.validate(root)
    assert any("FILE NOT IN MANIFEST" in finding for finding in findings)
