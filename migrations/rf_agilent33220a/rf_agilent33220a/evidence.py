"""RFDS-008 evidence and diagnostics engine for :mod:`rf_agilent33220a`.

Every public keyword call is recorded as one *run* under ``results/session/
rf_agilent33220a/<timestamp>_<run_id>/`` (override the root with
``RFDS_EVIDENCE_ROOT``): one JSON Lines entry per event/operation/error, a
redacted argument record, every SCPI command/query/response as a protocol
trace, and, once the suite ends, a ``run_summary.json`` + ``evidence_manifest
.json`` pair with a SHA-256 hash per artifact. ``Export Diagnostic Bundle``
zips the whole thing up for troubleshooting.

Unlike ``rf_phidget_relay`` (which talks to a vendor SDK with no wire
protocol), this driver is SCPI-over-VISA with a clean ``Transport.write()``/
``Transport.query()`` boundary (see ``agilent33220a/transport.py``) — so
protocol tracing here is a single :class:`TracingTransport` wrapper around
whatever real ``Transport`` a connection uses, rather than call sites
scattered through every keyword. The core driver (``agilent33220a/``) never
imports this module — it only sees a plain ``Transport``-shaped object,
preserving this package's own architecture rule that the core driver owns
SCPI and never duplicates adapter-layer concerns.

This module implements the parts of RFDS-008 that make a concrete
troubleshooting difference here — structured, correlated, redacted evidence
with integrity hashes — and does not attempt platform-scale concerns the
standard also describes (log rotation/backpressure policy, crash-recovery
tooling, cryptographic signing, retention/archival automation, a
cross-driver shared package). See ``docs/logging_and_evidence.md``.

Robot Framework suite/test/keyword correlation is wired directly into
``Agilent33220ALibrary``'s own listener methods (``_start_suite``/``_end_test``/
etc. — it already sets ``ROBOT_LIBRARY_LISTENER = self``), not a separate
opt-in listener class.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import logging
import os
import platform
import socket
import sys
import threading
import time
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "1.0.0"

logger = logging.getLogger("rf_agilent33220a.evidence")

_SENSITIVE_KEY_MARKERS = (
    "password", "secret", "token", "api_key", "apikey", "credential", "auth",
    "security_code", "code",  # "code" also catches Set Calibration Security Code's `new_code` argument
)

_current_correlation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "rf_agilent33220a_correlation_id", default=None
)
_current_operation_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "rf_agilent33220a_operation_id", default=None
)
_current_suite_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "rf_agilent33220a_suite_id", default=None
)
_current_test_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "rf_agilent33220a_test_id", default=None
)
_current_keyword: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "rf_agilent33220a_keyword", default=None
)


def set_current_suite(suite_id: Optional[str]) -> None:
    _current_suite_id.set(suite_id)


def set_current_test(test_id: Optional[str]) -> None:
    _current_test_id.set(test_id)


def set_current_keyword(keyword_name: Optional[str]) -> None:
    _current_keyword.set(keyword_name)


# ---------------------------------------------------------------------------
# Time, identifiers, JSON safety, redaction (identical approach to rf_phidget_relay)
# ---------------------------------------------------------------------------

def _utc_now_iso() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _new_run_id() -> str:
    now = datetime.now(timezone.utc)
    return f"run-{now.strftime('%Y%m%dT%H%M%S')}.{now.microsecond // 1000:03d}Z-{uuid.uuid4().hex[:8]}"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    return repr(obj)


def _looks_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return redact_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return repr(value)


def redact_mapping(data: Mapping[str, Any]) -> dict:
    """Redact keys that look sensitive (RFDS-008 §29.3); recurse into nested mappings.

    Relevant here: ``Set Calibration Security Code`` takes a vendor security
    code — its argument is redacted automatically by this key-name match.
    """
    result: dict = {}
    for key, value in data.items():
        if _looks_sensitive(str(key)):
            result[key] = {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
        else:
            result[key] = _json_safe(value)
    return result


def _classify_exception(exc: BaseException) -> str:
    """Approximate error category from this driver's own exception hierarchy.

    RFDS-008 §17 calls for RFDS-007 error categories/codes; RFDS-007 was not
    available while writing this, so this maps
    ``agilent33220a/exceptions.py``'s own names to a small stable category
    set instead of inventing RFDS-007 codes.
    """
    name = type(exc).__name__
    if "Configuration" in name:
        return "ENVIRONMENT"
    if "Validation" in name:
        return "VALIDATION"
    if "Connection" in name:
        return "STATE"
    if "Timeout" in name:
        return "HARDWARE"
    if "Protocol" in name:
        return "HARDWARE"
    if "Device" in name:
        return "HARDWARE"
    if "Safety" in name:
        return "VALIDATION"
    return "UNKNOWN"


def _safe_distribution_version(dist_name: str) -> Optional[str]:
    try:
        import importlib.metadata as importlib_metadata

        return importlib_metadata.version(dist_name)
    except Exception:
        return None


def _safe_module_version(module_name: str) -> Optional[str]:
    try:
        module = __import__(module_name)
        return getattr(module, "__version__", None)
    except Exception:
        return None


def _sanitized_hostname() -> str:
    try:
        return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:12]
    except Exception:
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# Protocol tracing: wraps any agilent33220a.transport.Transport
# ---------------------------------------------------------------------------

class TracingTransport:
    """Wraps a real ``Transport`` (Pyvisa or Simulated) with RFDS-008 protocol tracing.

    Implements the same duck-typed ``Transport`` protocol
    (``open``/``close``/``is_open``/``write``/``query``/``resource``/
    ``timeout_s``) so it's a drop-in replacement — ``agilent33220a/driver.py``
    calls ``self.transport.write(...)``/``.query(...)`` exactly as before and
    is never aware tracing is happening. Every ``write``/``query`` is logged
    as one outbound protocol exchange, and every ``query`` response as one
    inbound exchange, both correlated to whichever keyword operation is
    currently in progress (via the run's operation/correlation contextvars).
    """

    def __init__(self, inner: Any, evidence_run: "EvidenceRun", *, session_alias: Optional[str] = None) -> None:
        self._inner = inner
        self._evidence = evidence_run
        self._session_alias = session_alias

    @property
    def wrapped(self) -> Any:
        """The real transport underneath — used by callers that need its true type."""
        return self._inner

    @property
    def resource(self) -> str:
        return self._inner.resource

    def open(self) -> None:
        self._inner.open()

    def close(self) -> None:
        self._inner.close()

    def is_open(self) -> bool:
        return self._inner.is_open()

    def write(self, command: str) -> None:
        self._evidence.log_protocol("outbound", "scpi", command, session_alias=self._session_alias)
        self._inner.write(command)

    def query(self, command: str) -> str:
        self._evidence.log_protocol("outbound", "scpi", command, session_alias=self._session_alias)
        response = self._inner.query(command)
        self._evidence.log_protocol("inbound", "scpi", response, session_alias=self._session_alias)
        return response

    @property
    def timeout_s(self) -> float:
        return self._inner.timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        self._inner.timeout_s = value


def unwrap_transport(transport: Any) -> Any:
    """Return the real transport underneath a :class:`TracingTransport`, or ``transport`` itself."""
    return getattr(transport, "wrapped", transport)


# ---------------------------------------------------------------------------
# Operation context handed to callers inside a `with run.record_operation(...)` block
# ---------------------------------------------------------------------------

class _OperationContext:
    def __init__(self) -> None:
        self.result: Any = None

    def set_result(self, value: Any) -> None:
        self.result = value


class _NullOperationContext:
    def set_result(self, value: Any) -> None:  # pragma: no cover - trivial
        pass


# ---------------------------------------------------------------------------
# EvidenceRun
# ---------------------------------------------------------------------------

class EvidenceRun:
    """Owns one RFDS-008 result directory for one suite's ``Agilent33220ALibrary`` instance.

    One run covers the whole suite (``ROBOT_LIBRARY_SCOPE = "SUITE"``), which
    may connect/disconnect several aliased generators over its life — each
    operation/protocol record carries its own ``session_alias`` rather than
    the run being scoped to one connection.
    """

    SCHEMA = "rfds.run_summary"

    def __init__(
        self,
        *,
        driver_id: str = "rf_agilent33220a",
        activity: str = "session",
        result_root: Optional[Path] = None,
        execution_mode: str = "NO_HARDWARE",
    ) -> None:
        self.run_id = _new_run_id()
        self.driver_id = driver_id
        self.activity = activity
        # Starts NO_HARDWARE (no connection made yet) and is upgraded by
        # note_connection_mode() as Connect calls happen — never just defaults
        # to REAL_HARDWARE, since a run whose every connection was
        # simulated=True must not claim otherwise (RFDS-008 §6.6 simulation
        # honesty). See note_connection_mode() for the aggregation rule.
        self.execution_mode = execution_mode
        self._saw_simulated = False
        self._saw_real = False
        base = result_root or Path(os.environ.get("RFDS_EVIDENCE_ROOT", "results"))
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.root = base / activity / driver_id / f"{timestamp}_{self.run_id}"
        self._lock = threading.Lock()
        self._sequence: dict[str, int] = {}
        self._operation_counter = 0
        self._error_counter = 0
        self._start_monotonic = time.monotonic()
        self._start_time = _utc_now_iso()
        self._error_count = 0
        self._warning_count = 0
        self._finalized = False
        self._device_identity: dict = {}
        self._make_dirs()
        self._write_environment()
        self.emit_event("RUN_STARTED", f"Evidence run started for driver {driver_id}", level="INFO")

    def note_connection_mode(self, simulated: bool) -> None:
        """Call once per successful ``Connect`` with whether that connection was simulated.

        Aggregates across every connection this run has made so far:
        all-simulated -> ``SIMULATOR``, all-real -> ``REAL_HARDWARE``,
        a mix -> ``MIXED``. Never silently reverts to a more "impressive"
        mode once downgraded.
        """
        if simulated:
            self._saw_simulated = True
        else:
            self._saw_real = True
        if self._saw_simulated and self._saw_real:
            self.execution_mode = "MIXED"
        elif self._saw_simulated:
            self.execution_mode = "SIMULATOR"
        elif self._saw_real:
            self.execution_mode = "REAL_HARDWARE"

    def _make_dirs(self) -> None:
        for sub in ("events", "protocol", "cleanup", "integrity", "attachments"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

    def _write_environment(self) -> None:
        payload = {
            "schema": "rfds.environment",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "timestamp_utc": _utc_now_iso(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "host_token": _sanitized_hostname(),
            "robot_framework_version": _safe_module_version("robot"),
            "driver_distribution_version": _safe_distribution_version("robotframework-agilent33220a")
            or _safe_distribution_version("rf-agilent33220a"),
            "driver_source_version": _safe_module_version("agilent33220a"),
            # execution_mode is deliberately not captured here: it's not known until
            # at least one Connect happens (this file is written at run start, before
            # any). run_summary.json's execution_mode is the authoritative,
            # finalize-time value — see note_connection_mode().
            "clock_synchronization": "UNKNOWN",
        }
        self._write_json(self.root / "environment.json", payload)

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8"
            )

    def _append_jsonl(self, path: Path, stream_key: str, record: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            seq = self._sequence[stream_key] = self._sequence.get(stream_key, 0) + 1
            record = dict(record)
            record["sequence"] = seq
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=_json_default) + "\n")

    def emit_event(
        self,
        event_type: str,
        message: str,
        *,
        level: str = "INFO",
        data: Optional[Mapping[str, Any]] = None,
        correlation_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        session_alias: Optional[str] = None,
    ) -> None:
        record = {
            "schema": "rfds.event",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "producer_id": f"rf_agilent33220a:{session_alias or self.driver_id}",
            "timestamp_utc": _utc_now_iso(),
            "monotonic_ns": time.monotonic_ns(),
            "level": level,
            "event_type": event_type,
            "correlation_id": correlation_id or _current_correlation_id.get(),
            "operation_id": operation_id or _current_operation_id.get(),
            "source": {
                "component": "driver",
                "driver_id": self.driver_id,
                "session_alias": session_alias,
                "suite_id": _current_suite_id.get(),
                "test_id": _current_test_id.get(),
                "robot_keyword": _current_keyword.get(),
            },
            "message": message,
            "data": redact_mapping(dict(data or {})),
        }
        self._append_jsonl(self.root / "events" / "events.jsonl", "events", record)
        python_level = {
            "TRACE": logging.DEBUG,
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARN": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }.get(level, logging.INFO)
        logger.log(python_level, "[%s] %s", event_type, message)
        if level == "WARN":
            self._warning_count += 1
        # ERROR/CRITICAL not counted here: record_error() is the sole owner of
        # _error_count (every current ERROR-level emit_event call is paired with
        # a record_error() call — counting both would double-count each failure).

    @contextlib.contextmanager
    def record_operation(
        self,
        capability: str,
        *,
        arguments: Optional[Mapping[str, Any]] = None,
        session_alias: Optional[str] = None,
    ):
        with self._lock:
            self._operation_counter += 1
            operation_id = f"op-{self._operation_counter:06d}"
        correlation_id = _current_correlation_id.get() or f"corr-{uuid.uuid4().hex[:12]}"
        corr_token = _current_correlation_id.set(correlation_id)
        op_token = _current_operation_id.set(operation_id)
        safe_arguments = redact_mapping(dict(arguments or {}))
        start_monotonic = time.monotonic_ns()
        start_time = _utc_now_iso()
        self.emit_event(
            "OPERATION_STARTED", f"{capability} started", level="DEBUG",
            correlation_id=correlation_id, operation_id=operation_id,
            data={"arguments": safe_arguments}, session_alias=session_alias,
        )
        ctx = _OperationContext()
        status = "PASS"
        error_summary: Optional[str] = None
        try:
            yield ctx
        except Exception as exc:
            status = "FAIL"
            error_summary = f"{type(exc).__name__}: {exc}"
            self.record_error(
                exc, correlation_id=correlation_id, operation_id=operation_id,
                capability=capability, session_alias=session_alias,
            )
            raise
        finally:
            duration_s = (time.monotonic_ns() - start_monotonic) / 1e9
            record = {
                "schema": "rfds.operation",
                "schema_version": SCHEMA_VERSION,
                "run_id": self.run_id,
                "operation_id": operation_id,
                "correlation_id": correlation_id,
                "capability": capability,
                "session_alias": session_alias,
                "arguments": safe_arguments,
                "start_timestamp_utc": start_time,
                "end_timestamp_utc": _utc_now_iso(),
                "duration_s": round(duration_s, 6),
                "result": _json_safe(ctx.result) if status == "PASS" else None,
                "status": status,
                "error_summary": error_summary,
            }
            self._append_jsonl(self.root / "events" / "operations.jsonl", "operations", record)
            self.emit_event(
                "OPERATION_COMPLETED" if status == "PASS" else "OPERATION_FAILED",
                f"{capability} {'completed' if status == 'PASS' else 'failed'} in {duration_s:.4f}s",
                level="INFO" if status == "PASS" else "ERROR",
                correlation_id=correlation_id, operation_id=operation_id, session_alias=session_alias,
            )
            _current_correlation_id.reset(corr_token)
            _current_operation_id.reset(op_token)

    def log_protocol(
        self, direction: str, transport: str, operation_text: str, *, session_alias: Optional[str] = None
    ) -> None:
        if direction not in ("outbound", "inbound"):
            raise ValueError("direction must be 'outbound' or 'inbound'")
        exchange_id = f"pex-{uuid.uuid4().hex[:10]}"
        record = {
            "schema": "rfds.protocol_exchange",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "protocol_exchange_id": exchange_id,
            "operation_id": _current_operation_id.get(),
            "correlation_id": _current_correlation_id.get(),
            "timestamp_utc": _utc_now_iso(),
            "transport": transport,
            "direction": direction,
            "session_alias": session_alias,
            "operation": operation_text,
        }
        self._append_jsonl(self.root / "protocol" / "exchanges.jsonl", "protocol_exchanges", record)
        trace_path = self.root / "protocol" / f"{direction}_trace.log"
        with self._lock:
            with trace_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{record['timestamp_utc']} [{exchange_id}] {operation_text}\n")

    def record_error(
        self,
        exc: BaseException,
        *,
        correlation_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        capability: Optional[str] = None,
        session_alias: Optional[str] = None,
        recoverable: Optional[bool] = None,
    ) -> None:
        with self._lock:
            self._error_counter += 1
            error_id = f"err-{self._error_counter:06d}"
        record = {
            "schema": "rfds.error",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "error_id": error_id,
            "timestamp_utc": _utc_now_iso(),
            "correlation_id": correlation_id or _current_correlation_id.get(),
            "operation_id": operation_id or _current_operation_id.get(),
            "capability": capability,
            "session_alias": session_alias,
            "category": _classify_exception(exc),
            "exception_type": type(exc).__qualname__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "recoverable": recoverable,
        }
        self._append_jsonl(self.root / "events" / "errors.jsonl", "errors", record)
        self._error_count += 1
        logger.error("[%s] %s (%s): %s", error_id, capability or "?", type(exc).__name__, exc)

    def record_device_identity(self, session_alias: str, **fields: Any) -> None:
        """Per-alias identity, merged into ``device_identity.json`` under that alias.

        Several aliased generators may be connected within one run, so this
        is a dict of alias -> identity rather than one flat record.
        """
        self._device_identity[session_alias] = {
            key: value for key, value in fields.items() if value is not None
        }
        payload = {
            "schema": "rfds.device_identity",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "timestamp_utc": _utc_now_iso(),
            "connections": self._device_identity,
        }
        self._write_json(self.root / "device_identity.json", payload)

    def _write_manifest(self) -> None:
        skip_names = {"evidence_manifest.json", "checksums.sha256"}
        entries = []
        for path in sorted(self.root.rglob("*")):
            if path.is_dir() or path.name in skip_names:
                continue
            relative = path.relative_to(self.root)
            data = path.read_bytes()
            entries.append(
                {
                    "path": str(relative).replace(os.sep, "/"),
                    "role": _role_for(relative),
                    "size_bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        manifest = {
            "schema": "rfds.evidence_manifest",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "generated_timestamp_utc": _utc_now_iso(),
            "artifact_count": len(entries),
            "artifacts": entries,
        }
        self._write_json(self.root / "evidence_manifest.json", manifest)
        checksum_path = self.root / "integrity" / "checksums.sha256"
        checksum_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            checksum_path.write_text(
                "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in entries), encoding="utf-8"
            )

    def finalize(self, status: str = "PASS") -> Path:
        if self._finalized:
            return self.root
        self.emit_event("RUN_FINISHING", f"Evidence run finalizing with status {status}", level="INFO")
        duration_s = time.monotonic() - self._start_monotonic
        summary = {
            "schema": self.SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "activity": self.activity,
            "driver_id": self.driver_id,
            "start_timestamp_utc": self._start_time,
            "end_timestamp_utc": _utc_now_iso(),
            "duration_s": round(duration_s, 3),
            "execution_mode": self.execution_mode,
            "final_status": status,
            "error_count": self._error_count,
            "warning_count": self._warning_count,
            "dropped_events": 0,
            "evidence_completeness": "COMPLETE",
            "device_identity_reference": "device_identity.json" if self._device_identity else None,
            "result_root": str(self.root),
        }
        self._write_json(self.root / "run_summary.json", summary)
        self._write_markdown_summary(summary)
        self._write_manifest()
        self._finalized = True
        return self.root

    def _write_markdown_summary(self, summary: dict) -> None:
        lines = [
            f"# Evidence run summary — {summary['driver_id']}",
            "",
            f"- Run ID: `{summary['run_id']}`",
            f"- Activity: {summary['activity']}",
            f"- Execution mode: {summary['execution_mode']}",
            f"- Started: {summary['start_timestamp_utc']}",
            f"- Finished: {summary['end_timestamp_utc']}",
            f"- Duration: {summary['duration_s']} s",
            f"- Final status: **{summary['final_status']}**",
            f"- Errors: {summary['error_count']}, Warnings: {summary['warning_count']}",
            f"- Evidence completeness: {summary['evidence_completeness']}",
            "",
            "Generated from `run_summary.json`. See `events/operations.jsonl` for every",
            "keyword call this run made, `events/errors.jsonl` for failures, and",
            "`protocol/exchanges.jsonl` for the underlying SCPI commands/responses, in the",
            "order they happened.",
            "",
        ]
        (self.root / "run_summary.md").write_text("\n".join(lines), encoding="utf-8")

    def export_diagnostic_bundle(self, destination: Optional[str] = None) -> str:
        self._write_manifest()
        if destination:
            zip_path = Path(destination)
            zip_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            zip_path = self.root.parent / f"{self.root.name}_diagnostic_bundle.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(self.root.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(Path(self.root.name) / path.relative_to(self.root)))
        self.emit_event("DIAGNOSTIC_BUNDLE_EXPORTED", f"Diagnostic bundle written to {zip_path}", level="INFO")
        return str(zip_path)


_ROLE_BY_NAME = {
    "run_summary.json": "AUTHORITATIVE_RESULT",
    "run_summary.md": "DERIVED_REPORT",
    "environment.json": "IDENTITY",
    "device_identity.json": "IDENTITY",
}


def _role_for(relative_path: Path) -> str:
    name = relative_path.name
    if name in _ROLE_BY_NAME:
        return _ROLE_BY_NAME[name]
    parts = relative_path.parts
    if parts and parts[0] == "protocol":
        return "RAW_OBSERVATION"
    if relative_path.suffix == ".jsonl":
        return "STRUCTURED_EVENT"
    if parts and parts[0] == "integrity":
        return "INTEGRITY"
    return "DERIVED_REPORT"


class NullEvidenceRun:
    """Used when ``evidence_enabled=False``: same interface, writes nothing to disk."""

    run_id: Optional[str] = None

    @contextlib.contextmanager
    def record_operation(self, capability: str, *, arguments=None, session_alias=None):
        logger.debug("%s(%s)", capability, dict(arguments or {}))
        yield _NullOperationContext()

    def emit_event(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def log_protocol(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def record_error(self, exc: BaseException, **_kwargs: Any) -> None:
        logger.error("%s: %s", type(exc).__name__, exc)

    def record_device_identity(self, session_alias: str, **_kwargs: Any) -> None:
        pass

    def note_connection_mode(self, simulated: bool) -> None:
        pass

    def finalize(self, status: str = "PASS") -> None:
        return None

    def export_diagnostic_bundle(self, destination: Optional[str] = None) -> None:
        logger.warning("Diagnostic bundle requested but evidence_enabled=False; nothing was recorded.")
        return None


__all__ = [
    "SCHEMA_VERSION",
    "EvidenceRun",
    "NullEvidenceRun",
    "TracingTransport",
    "unwrap_transport",
    "redact_mapping",
    "set_current_suite",
    "set_current_test",
    "set_current_keyword",
]
