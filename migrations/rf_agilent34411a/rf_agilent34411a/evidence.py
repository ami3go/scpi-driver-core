"""RFDS-008 evidence and diagnostics engine for :mod:`rf_agilent34411a`.

Every public keyword call is recorded as an RFDS-008 evidence *run* — one per
``Agilent34411ALibrary`` instance (this library is ``ROBOT_LIBRARY_SCOPE =
"SUITE"``, so normally one run per suite), written to
``results/session/rf_agilent34411a/<run>/`` (override with
``RFDS_EVIDENCE_ROOT``). Unlike a single-session driver, this library
supports multiple simultaneously connected aliases (``Connect ... alias=B``),
so evidence is not finalized when any one alias disconnects — it is
finalized in ``_end_suite`` (Robot's own suite-end listener hook, already
wired via ``ROBOT_LIBRARY_LISTENER = self`` in ``library.py``), which is the
one point that reliably fires once regardless of how many aliases were used.

Protocol tracing hooks in at the transport boundary: :class:`InstrumentedTransport`
wraps the core driver's real ``Transport`` (VISA or simulated, see
``agilent34411a/transport.py``) and logs every ``write``/``query`` call
verbatim — this is the same instrumented-transport approach RFDS-019 §10
describes ("transport spy or wrapper"), and it means every SCPI command this
driver issues is captured without editing a single line of the core driver
or its transport implementations (RFDS-004: core driver code never touches
evidence/logging concerns, only the RF adapter layer does).

This is a self-contained module (no shared package exists yet in this
repository — see ``rf_phidget_relay/docs/logging_and_evidence.md``, "what
this system deliberately does not do"); it was adapted from the equivalent
module built for ``rf_phidget_relay``, with the transport-boundary tracing
and multi-alias finalization changed to match this driver's actual
architecture rather than copied mechanically.
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
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"

logger = logging.getLogger("rf_agilent34411a.evidence")

_SENSITIVE_KEY_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential", "auth")

_current_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_agilent34411a_correlation_id", default=None
)
_current_operation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_agilent34411a_operation_id", default=None
)
_current_suite_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_agilent34411a_suite_id", default=None
)
_current_test_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_agilent34411a_test_id", default=None
)
_current_keyword: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_agilent34411a_keyword", default=None
)


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
    """Redact keys that look sensitive; recurse into nested mappings (RFDS-008 §29.3)."""
    result: dict = {}
    for key, value in data.items():
        if _looks_sensitive(str(key)):
            result[key] = {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
        else:
            result[key] = _json_safe(value)
    return result


def _classify_exception(exc: BaseException) -> str:
    """Approximate error category from this driver's RFDS-007 exception hierarchy.

    Maps ``agilent34411a/exceptions.py`` names to a small stable category set;
    RFDS-007 codes proper were not available while writing this.
    """
    name = type(exc).__name__
    if "Overload" in name:
        return "OUT_OF_RANGE"
    if "Configuration" in name or "Validation" in name:
        return "VALIDATION"
    if "Connection" in name:
        return "CONNECTION"
    if "Timeout" in name:
        return "TIMEOUT"
    if "Protocol" in name:
        return "PROTOCOL"
    if "Device" in name:
        return "DEVICE"
    return "UNKNOWN"


def _safe_distribution_version(dist_name: str) -> str | None:
    try:
        import importlib.metadata as importlib_metadata

        return importlib_metadata.version(dist_name)
    except Exception:  # noqa: BLE001 - best-effort diagnostic only, never worth failing evidence capture over
        return None


def _safe_module_version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
        return getattr(module, "__version__", None)
    except Exception:  # noqa: BLE001 - best-effort diagnostic only, never worth failing evidence capture over
        return None


def _sanitized_hostname() -> str:
    try:
        return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:12]
    except Exception:  # noqa: BLE001 - hostname sanitization must never fail run creation
        return "UNKNOWN"


class _OperationContext:
    def __init__(self) -> None:
        self.result: Any = None

    def set_result(self, value: Any) -> None:
        self.result = value


class _NullOperationContext:
    def set_result(self, value: Any) -> None:  # pragma: no cover - trivial
        pass


class EvidenceRun:
    """Owns one RFDS-008 result directory for one Agilent34411ALibrary instance."""

    SCHEMA = "rfds.run_summary"

    def __init__(
        self,
        *,
        driver_id: str,
        activity: str = "session",
        result_root: Path | None = None,
        execution_mode: str = "REAL_HARDWARE",
    ) -> None:
        self.run_id = _new_run_id()
        self.driver_id = driver_id
        self.activity = activity
        self.execution_mode = execution_mode
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
            "driver_distribution_version": _safe_distribution_version("robotframework-agilent34411a"),
            "driver_source_version": _safe_module_version("agilent34411a"),
            "execution_mode": self.execution_mode,
            "clock_synchronization": "UNKNOWN",
        }
        self._write_json(self.root / "environment.json", payload)

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            path.write_text(
                json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
                encoding="utf-8",
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
        data: Mapping[str, Any] | None = None,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        session_alias: str | None = None,
    ) -> None:
        record = {
            "schema": "rfds.event",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "producer_id": f"rf_agilent34411a:{session_alias or self.driver_id}",
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
        # ERROR/CRITICAL are not counted here: paired record_error() calls own _error_count.

    @contextlib.contextmanager
    def record_operation(
        self,
        capability: str,
        *,
        arguments: Mapping[str, Any] | None = None,
        session_alias: str | None = None,
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
            "OPERATION_STARTED",
            f"{capability} started",
            level="DEBUG",
            correlation_id=correlation_id,
            operation_id=operation_id,
            data={"arguments": safe_arguments},
            session_alias=session_alias,
        )
        ctx = _OperationContext()
        status = "PASS"
        error_summary: str | None = None
        try:
            yield ctx
        except Exception as exc:
            status = "FAIL"
            error_summary = f"{type(exc).__name__}: {exc}"
            self.record_error(
                exc,
                correlation_id=correlation_id,
                operation_id=operation_id,
                capability=capability,
                session_alias=session_alias,
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
                correlation_id=correlation_id,
                operation_id=operation_id,
                session_alias=session_alias,
            )
            _current_correlation_id.reset(corr_token)
            _current_operation_id.reset(op_token)

    def log_protocol(
        self,
        direction: str,
        transport: str,
        operation_text: str,
        *,
        session_alias: str | None = None,
    ) -> None:
        """Record one outbound SCPI command/query or inbound response.

        ``direction`` is ``"outbound"`` (driver -> instrument) or
        ``"inbound"`` (instrument -> driver). See :class:`InstrumentedTransport`
        for where this is actually called from.
        """
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
        with self._lock, trace_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{record['timestamp_utc']} [{exchange_id}] {operation_text}\n")

    def record_error(
        self,
        exc: BaseException,
        *,
        correlation_id: str | None = None,
        operation_id: str | None = None,
        capability: str | None = None,
        session_alias: str | None = None,
        recoverable: bool | None = None,
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

    def record_device_identity(self, *, session_alias: str, **fields: Any) -> None:
        """Multi-alias aware: keeps one identity block per alias in device_identity.json."""
        self._device_identity[session_alias] = {
            key: value for key, value in fields.items() if value is not None
        }
        payload = {
            "schema": "rfds.device_identity",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "timestamp_utc": _utc_now_iso(),
            "sessions": self._device_identity,
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
            "Generated from `run_summary.json`. See `events/operations.jsonl` for every keyword",
            "call this run made (each tagged with the `alias` it targeted), `events/errors.jsonl`",
            "for failures, and `protocol/exchanges.jsonl` for the underlying SCPI commands and",
            "responses, in the order they happened.",
            "",
        ]
        (self.root / "run_summary.md").write_text("\n".join(lines), encoding="utf-8")

    def export_diagnostic_bundle(self, destination: str | None = None) -> str:
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

    run_id: str | None = None

    @contextlib.contextmanager
    def record_operation(self, capability: str, *, arguments: Mapping[str, Any] | None = None, session_alias=None):
        logger.debug("%s(%s)", capability, dict(arguments or {}))
        yield _NullOperationContext()

    def emit_event(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def log_protocol(self, *_args: Any, **_kwargs: Any) -> None:
        pass

    def record_error(self, exc: BaseException, **_kwargs: Any) -> None:
        logger.error("%s: %s", type(exc).__name__, exc)

    def record_device_identity(self, **_kwargs: Any) -> None:
        pass

    def finalize(self, status: str = "PASS") -> None:
        return None

    def export_diagnostic_bundle(self, destination: str | None = None) -> None:
        logger.warning("Diagnostic bundle requested but evidence_enabled=False; nothing was recorded.")


class InstrumentedTransport:
    """Wraps any ``agilent34411a.transport.Transport`` and traces every write/query.

    RFDS-019 §10 "transport spy or wrapper": sits directly at the protocol
    boundary, so it observes exactly what the core driver attempted to
    transmit and exactly what it received, without changing core driver or
    transport code. Everything not explicitly overridden below (``resource``,
    ``timeout_s`` getter, ``.simulator`` on ``SimulatedTransport``, ...)
    delegates transparently via ``__getattr__``.
    """

    def __init__(self, inner: Any, evidence_run: EvidenceRun | NullEvidenceRun, session_alias: str) -> None:
        self._inner = inner
        self._evidence_run = evidence_run
        self._session_alias = session_alias

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def open(self) -> None:
        self._inner.open()

    def close(self) -> None:
        self._inner.close()

    def is_open(self) -> bool:
        return self._inner.is_open()

    def write(self, command: str) -> None:
        self._evidence_run.log_protocol("outbound", "scpi", command, session_alias=self._session_alias)
        self._inner.write(command)

    def query(self, command: str) -> str:
        self._evidence_run.log_protocol("outbound", "scpi", command, session_alias=self._session_alias)
        response = self._inner.query(command)
        self._evidence_run.log_protocol("inbound", "scpi", response, session_alias=self._session_alias)
        return response

    @property
    def timeout_s(self) -> float:
        return self._inner.timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        self._inner.timeout_s = value


class EvidenceListener:
    """Register with ``--listener rf_agilent34411a.evidence.EvidenceListener``.

    Populates the suite/test/keyword identifiers attached to every event's
    ``source`` block. Entirely optional — the evidence engine works without it.
    """

    ROBOT_LISTENER_API_VERSION = 3

    def start_suite(self, data: Any, result: Any) -> None:
        _current_suite_id.set(getattr(data, "longname", str(data)))

    def end_suite(self, data: Any, result: Any) -> None:
        _current_suite_id.set(None)

    def start_test(self, data: Any, result: Any) -> None:
        _current_test_id.set(getattr(data, "longname", str(data)))

    def end_test(self, data: Any, result: Any) -> None:
        _current_test_id.set(None)

    def start_keyword(self, data: Any, result: Any) -> None:
        _current_keyword.set(getattr(data, "name", str(data)))

    def end_keyword(self, data: Any, result: Any) -> None:
        _current_keyword.set(None)


__all__ = [
    "SCHEMA_VERSION",
    "EvidenceListener",
    "EvidenceRun",
    "InstrumentedTransport",
    "NullEvidenceRun",
    "redact_mapping",
]
