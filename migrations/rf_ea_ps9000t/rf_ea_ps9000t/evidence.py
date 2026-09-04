"""RFDS-008 evidence and diagnostics engine for :mod:`rf_ea_ps9000t`.

Every public keyword call is recorded as a *run* under ``results/session/
rf_ea_ps9000t/<timestamp>_<run_id>/`` (override the root with the
``RFDS_EVIDENCE_ROOT`` environment variable): one JSON Lines entry per
event/operation/error, a redacted argument record, the raw SCPI commands and
responses as a protocol trace (via :class:`TracingTransport`, wrapped around
the core driver's ``Transport`` after ``Connect``), an instrument-identity
snapshot, and, once ``Disconnect`` runs for that alias, a
``run_summary.json`` + ``evidence_manifest.json`` pair with a SHA-256 hash
per artifact. ``Export Diagnostic Bundle`` zips the whole thing up for
sending to whoever is troubleshooting a failure.

Since ``EaPs9000TLibrary`` supports multiple concurrently-connected named
sessions (the ``alias`` parameter accepted by every keyword — see
``rf_ea_ps9000t/library.py``), evidence is tracked **per alias**: each
``Connect`` call gets its own :class:`EvidenceRun`, keyed by the resolved
alias, and each ``Disconnect`` finalizes and removes only that alias's run.
Keywords called with no active alias yet (e.g. ``Get Active Power Supply``
before any ``Connect``) fall back to a shared ``"__unbound__"`` bucket run
that is never explicitly finalized (see ``docs/logging_and_evidence.md``).

This module intentionally implements the parts of RFDS-008 that make a
concrete troubleshooting difference for this driver — structured, correlated,
redacted evidence with integrity hashes and a real SCPI trace — and does not
attempt platform-scale concerns the standard also describes (log
rotation/backpressure policy, crash-recovery tooling, cryptographic signing,
retention/archival automation, a cross-driver shared package). Those are
noted inline where relevant rather than silently skipped. This module was
adapted from the equivalent one built for ``rf_phidget_relay``; the only
driver-specific pieces are :class:`TracingTransport`, ``_classify_exception``,
and the version-lookup names in ``_write_environment``.

Nothing here talks to Robot Framework directly except :class:`EvidenceListener`,
which is optional (register with ``--listener
rf_ea_ps9000t.evidence.EvidenceListener`` to correlate events with the active
suite/test/keyword); the engine itself works the same under plain pytest.
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

logger = logging.getLogger("rf_ea_ps9000t.evidence")

_SENSITIVE_KEY_MARKERS = ("password", "secret", "token", "api_key", "apikey", "credential", "auth")

# Correlates nested/related operations and Robot Framework context without
# threading an explicit parameter through every driver method.
_current_correlation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_ea_ps9000t_correlation_id", default=None
)
_current_operation_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_ea_ps9000t_operation_id", default=None
)
_current_suite_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_ea_ps9000t_suite_id", default=None
)
_current_test_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_ea_ps9000t_test_id", default=None
)
_current_keyword: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "rf_ea_ps9000t_keyword", default=None
)


# ---------------------------------------------------------------------------
# Time, identifiers, JSON safety
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
    """Redact keys that look sensitive; recurse into nested mappings.

    RFDS-008 §29.3 redaction marker shape. Sensitivity is judged by key name
    only (``password``, ``token``, ``secret``, ...) — this driver has no
    credential-bearing arguments today (LAN configuration keywords carry
    hostnames/addresses, not secrets), but keyword arguments are logged
    generically enough that a future one would be caught automatically.
    """
    result: dict = {}
    for key, value in data.items():
        if _looks_sensitive(str(key)):
            result[key] = {"value": "<REDACTED>", "redacted": True, "reason": "credential"}
        else:
            result[key] = _json_safe(value)
    return result


def _classify_exception(exc: BaseException) -> str:
    """Approximate error category from this driver's exception hierarchy.

    RFDS-008 §17 calls for "RFDS error category and code defined by
    RFDS-007"; RFDS-007 itself was not available while writing this, so this
    maps the driver's own exception names (``ea_ps9000t/exceptions.py``) to a
    small stable category set instead of inventing RFDS-007 codes.
    """
    name = type(exc).__name__
    if "Configuration" in name or "Validation" in name:
        return "VALIDATION"
    if "Connection" in name:
        return "STATE"
    if "Timeout" in name:
        return "HARDWARE"
    if "Protocol" in name:
        return "HARDWARE"
    if "Device" in name:
        return "HARDWARE"
    return "UNKNOWN"


def _safe_distribution_version(dist_name: str) -> str | None:
    try:
        import importlib.metadata as importlib_metadata

        return importlib_metadata.version(dist_name)
    except Exception:  # noqa: BLE001 - best-effort version lookup, never worth failing evidence for
        return None


def _safe_module_version(module_name: str) -> str | None:
    try:
        module = __import__(module_name)
        return getattr(module, "__version__", None)
    except Exception:  # noqa: BLE001 - best-effort version lookup, never worth failing evidence for
        return None


def _sanitized_hostname() -> str:
    """A stable, non-reversible token instead of the raw hostname (RFDS-008 §19.5/§29.2)."""
    try:
        return hashlib.sha256(socket.gethostname().encode("utf-8")).hexdigest()[:12]
    except Exception:  # noqa: BLE001 - best-effort; a failed hostname lookup must not break evidence
        return "UNKNOWN"


# ---------------------------------------------------------------------------
# TracingTransport — the SCPI protocol-boundary observation point (RFDS-019 §10)
# ---------------------------------------------------------------------------

class TracingTransport:
    """Wraps any ``ea_ps9000t.transport.Transport`` and logs every SCPI
    write/query to an :class:`EvidenceRun`, without changing behavior.

    Implements the same duck-typed ``Transport`` protocol (``open``,
    ``close``, ``is_open``, ``write``, ``query``, ``resource``,
    ``timeout_s``) by forwarding every call to the wrapped transport, so it
    is a drop-in replacement assignable to ``EaPs9000T.transport`` after
    connecting. SCPI command construction and parsing stay entirely in
    ``ea_ps9000t.driver`` — this class only observes the text that crosses
    the transport boundary, matching RFDS-019 §10's requirement that trace
    capture sit "close enough to the device boundary to prove what the
    driver attempted to transmit and what it received" without embedding
    protocol logic in the evidence layer.

    Known gap: because it wraps the transport *after* ``EaPs9000T.connect_visa``/
    ``connect_simulated`` return, the SCPI exchange for the initial
    ``acquire_remote_control()`` call made inside those classmethods is not
    traced at the byte level — only the surrounding ``Connect`` operation
    record (arguments/duration/success-or-failure) covers it. Wrapping
    earlier would require duplicating ``connect_visa``/``connect_simulated``'s
    transport-construction logic in the RF adapter, which was judged a worse
    trade-off than this documented gap.
    """

    def __init__(self, transport: Any, run: EvidenceRun, session_alias: str | None) -> None:
        self._transport = transport
        self._run = run
        self._session_alias = session_alias

    @property
    def resource(self) -> str:
        return self._transport.resource

    @resource.setter
    def resource(self, value: str) -> None:
        self._transport.resource = value

    @property
    def wrapped_type_name(self) -> str:
        """The real transport class name (``PyvisaTransport``/``SimulatedTransport``),
        for callers such as ``EaPs9000TLibrary._connection_state`` that report the
        transport type and must not leak this wrapper's own class name."""
        return type(self._transport).__name__

    def open(self) -> None:
        self._transport.open()

    def close(self) -> None:
        self._transport.close()

    def is_open(self) -> bool:
        return self._transport.is_open()

    def write(self, command: str) -> None:
        self._run.log_protocol("outbound", "scpi", command, session_alias=self._session_alias)
        self._transport.write(command)

    def query(self, command: str) -> str:
        self._run.log_protocol("outbound", "scpi", command, session_alias=self._session_alias)
        response = self._transport.query(command)
        self._run.log_protocol("inbound", "scpi", response, session_alias=self._session_alias)
        return response

    @property
    def timeout_s(self) -> float:
        return self._transport.timeout_s

    @timeout_s.setter
    def timeout_s(self, value: float) -> None:
        self._transport.timeout_s = value


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
    """Owns one RFDS-008 result directory for one driver session (one alias).

    Not thread-safe across concurrent *sessions* (each alias should own its
    own instance); writes from a single instance are internally serialized
    with a lock so overlapping keyword calls from Robot's own machinery don't
    interleave a JSONL line.
    """

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
        # Two independent counter spaces, kept deliberately separate: `_sequence`
        # is the per-JSONL-stream line-sequence counter (incremented only inside
        # `_append_jsonl`), while `_operation_counter`/`_error_counter` generate
        # operation_id/error_id values. Sharing one counter between "the Nth ID
        # issued" and "the Nth line written to this stream" produces gaps
        # whenever an ID is issued before its record is appended.
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

    # -- setup ----------------------------------------------------------

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
            "driver_distribution_version": _safe_distribution_version("robotframework-ea-ps9000t"),
            "driver_source_version": _safe_module_version("ea_ps9000t"),
            "pyvisa_distribution_version": _safe_distribution_version("pyvisa"),
            "execution_mode": self.execution_mode,
            "clock_synchronization": "UNKNOWN",
        }
        self._write_json(self.root / "environment.json", payload)

    # -- low-level writers ------------------------------------------------

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

    # -- public event/operation/error API --------------------------------

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
            "producer_id": f"rf_ea_ps9000t:{session_alias or self.driver_id}",
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
        # ERROR/CRITICAL events are not counted here: every current ERROR/CRITICAL
        # emit_event call is paired with a record_error() call, which is the sole
        # owner of _error_count — counting both here would double-count each failure.

    @contextlib.contextmanager
    def record_operation(
        self,
        capability: str,
        *,
        arguments: Mapping[str, Any] | None = None,
        session_alias: str | None = None,
    ):
        """Context manager recording one keyword/capability invocation.

        Yields an object with ``set_result(value)`` so the caller can record
        a JSON-safe return value. Writes one entry to ``events/operations.jsonl``
        covering both the success and failure path, and delegates to
        :meth:`record_error` on failure before re-raising — the original
        exception always propagates unchanged.
        """
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
        """Record one outbound/inbound SCPI exchange as protocol evidence.

        ``direction`` is ``"outbound"`` (driver -> device: a SCPI command or
        query) or ``"inbound"`` (device -> driver: a raw SCPI response).
        Called by :class:`TracingTransport`, the actual protocol-boundary
        observation point (RFDS-019 §10) — command construction/parsing
        never happens in this module.
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

    def record_device_identity(self, **fields: Any) -> None:
        self._device_identity.update({key: value for key, value in fields.items() if value is not None})
        payload = {
            "schema": "rfds.device_identity",
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "timestamp_utc": _utc_now_iso(),
            **self._device_identity,
        }
        self._write_json(self.root / "device_identity.json", payload)

    # -- finalization -------------------------------------------------

    def _write_manifest(self) -> None:
        """(Re)write evidence_manifest.json + integrity/checksums.sha256.

        Safe to call more than once (e.g. from ``Export Diagnostic Bundle``
        on a still-open run) — it always reflects whatever files currently
        exist under the result root.
        """
        # integrity/checksums.sha256 is excluded for the same reason
        # evidence_manifest.json is: both are derived *from* this file listing,
        # so re-including them here would make the manifest describe a stale
        # version of itself (self-referential hash mismatch) the moment either
        # is rewritten by a second finalize()/export_diagnostic_bundle() call.
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
        """Close out the run: write run_summary.json/.md and the evidence manifest.

        Idempotent — a second call is a no-op and returns the same root. Once
        finalized, further ``emit_event``/``record_operation`` calls still
        work (nothing here refuses to run) but will not be reflected in the
        already-written manifest; call :meth:`export_diagnostic_bundle`
        afterward if that matters.
        """
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
            "call this run made, `events/errors.jsonl` for failures, and `protocol/exchanges.jsonl`",
            "for the raw SCPI commands/responses, in the order they happened.",
            "",
        ]
        (self.root / "run_summary.md").write_text("\n".join(lines), encoding="utf-8")

    def export_diagnostic_bundle(self, destination: str | None = None) -> str:
        """Zip the current state of this run's result directory for sharing.

        Refreshes the manifest first (without finalizing the run), so this
        can be called mid-session to grab a snapshot while troubleshooting a
        problem that hasn't finished happening yet.
        """
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
    """Used when ``evidence_enabled=False``: same interface, writes nothing to disk.

    Errors are still sent to the standard Python logger so disabling evidence
    never silences the one thing every troubleshooting session needs first.
    """

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


# ---------------------------------------------------------------------------
# Optional Robot Framework listener — correlates events with suite/test/keyword
# ---------------------------------------------------------------------------

class EvidenceListener:
    """Register with ``--listener rf_ea_ps9000t.evidence.EvidenceListener``.

    Populates the suite/test/keyword identifiers that :meth:`EvidenceRun.emit_event`
    attaches to every event's ``source`` block. Entirely optional: the evidence
    engine works without it, just without Robot-side correlation. Independent
    of ``EaPs9000TLibrary``'s own ``_end_suite`` listener hook (registered via
    ``ROBOT_LIBRARY_LISTENER``), which finalizes any still-open evidence runs.
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
    "NullEvidenceRun",
    "TracingTransport",
    "redact_mapping",
]
