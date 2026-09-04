"""Robot Framework library for the NGI N83624 24-channel cell simulator.

The library wraps the typed :mod:`ngi_n83624` Python driver and adds Robot-specific
session management, input conversion, output arming, audit logging, assertions, and
safe teardown.

Every public keyword is wrapped (see ``_evidenced`` below) with an RFDS-008
evidence operation record — arguments, duration, result/failure, and a
correlated trace of the underlying SCPI write/query traffic — written per
connection alias to ``results/session/rf_ngi_n83624/<run>/``. This is a
separate, deeper layer than the existing opt-in ``audit_log_path`` JSONL
audit log; see ``evidence.py`` and ``docs/logging_and_evidence.md`` for how
the two relate. Pass ``evidence_enabled=${FALSE}`` to disable it.
"""

from __future__ import annotations

import functools
import inspect
import json
import math
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from robot.api import logger
from robot.api.deco import keyword, library

from ngi_n83624 import (
    CaptureRate,
    ChannelLimits,
    CurrentRange,
    DriverSafetyPolicy,
    HeartbeatConfig,
    InstrumentLimits,
    N83624CellSimulator,
    OutputMode,
    SequenceStep,
    SocStep,
)
from ngi_n83624.emulator import SimpleN83624Emulator
from ngi_n83624.exceptions import SafetyError, SessionStateError, ValidationError

from . import evidence as _evidence

RELEASE_VERSION = "26.02"
OUTPUT_CONFIRMATION = "ENABLE OUTPUT"
RAW_SCPI_CONFIRMATION = "ENABLE RAW SCPI"


@dataclass
class _Session:
    alias: str
    driver: N83624CellSimulator
    safe_shutdown: bool
    allow_raw_scpi: bool
    audit_log_path: Path | None
    armed_channels: set[int]
    emulator: SimpleN83624Emulator | None = None


def _evidenced(func: Callable) -> Callable:
    """Wrap a keyword method with an RFDS-008 evidence operation record.

    Resolves which connection alias's :class:`evidence.EvidenceRun` applies
    using the same "explicit alias, else active alias, else 'default'" rule
    as :meth:`NGI_N83624._session`, but tolerates the alias not existing yet
    (needed for ``Open N83624 * Connection``, where the session is created
    *during* the wrapped call). After every call, whichever aliases actually
    disappeared from ``self._sessions`` during the call have their evidence
    run finalized (see ``_finalize_closed_sessions``) — this naturally covers
    ``Close N83624 Connection`` and ``Close All N83624 Connections`` (which
    calls the former once per alias, itself wrapped) without special-casing
    either capability by name.

    Finalization is deferred to the outermost (non-nested) call only —
    detected via whether ``evidence._current_operation_id`` is already set on
    entry. Without this, ``Close All N83624 Connections`` calling the
    per-alias ``Close N83624 Connection`` internally would finalize (and
    hash-freeze) that alias's run *before* the outer call's own operation
    record is appended to it, leaving evidence_manifest.json describing a
    stale version of operations.jsonl.

    Must sit *below* ``@keyword(...)`` in the decorator stack — see the same
    note in ``rf_phidget_relay``'s ``_evidenced`` for why ``wrapper.robot_name``
    is safely readable at call time despite being set by a decorator that
    runs *after* this one.
    """
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(self: NGI_N83624, *args: Any, **kwargs: Any) -> Any:
        capability = getattr(wrapper, "robot_name", None) or func.__name__.replace("_", " ").title()
        bound = signature.bind_partial(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {key: value for key, value in bound.arguments.items() if key != "self"}
        resolved_alias = self._resolve_alias_for_evidence(arguments)
        execution_mode = "SIMULATOR" if capability == "Open N83624 Emulator" else "REAL_HARDWARE"
        run = self._ensure_evidence_run(resolved_alias, execution_mode=execution_mode)
        is_top_level_call = _evidence._current_operation_id.get() is None
        aliases_before = set(self._sessions)
        status = "PASS"
        try:
            with run.record_operation(capability, arguments=arguments, session_alias=resolved_alias) as op:
                result = func(self, *args, **kwargs)
                op.set_result(result)
            return result
        except Exception:
            status = "FAIL"
            raise
        finally:
            if is_top_level_call:
                self._finalize_closed_sessions(aliases_before, status)

    return wrapper


@library(scope="GLOBAL", version=RELEASE_VERSION, auto_keywords=False)
class NGI_N83624:
    """Robot Framework keyword library for NGI N83624 instruments.

    The library supports multiple named sessions. Real connections start with all
    output channels *disarmed*. Before enabling a channel, configure finite voltage
    and current limits and call ``Arm Channel Output`` with the exact confirmation
    text ``ENABLE OUTPUT``.

    ``safe_shutdown`` defaults to true. Closing a session then attempts to disable
    every channel even if one channel command fails, closes the transport, and clears
    the output arming state.
    """

    ROBOT_LIBRARY_LISTENER = None

    def __init__(
        self,
        default_host: str = "192.168.0.123",
        default_port: int = 7000,
        default_timeout: float = 3.0,
        auto_close_on_suite_end: bool = True,
        evidence_enabled: bool | str = True,
    ) -> None:
        self.default_host = str(default_host)
        self.default_port = self._as_int(default_port, "default_port")
        self.default_timeout = self._as_float(default_timeout, "default_timeout")
        self.auto_close_on_suite_end = self._as_bool(auto_close_on_suite_end)
        self._evidence_enabled = self._as_bool(evidence_enabled)
        self._sessions: dict[str, _Session] = {}
        self._evidence_runs: dict[str, Any] = {}
        self._active_alias: str | None = None
        self.ROBOT_LIBRARY_LISTENER = self
        self.ROBOT_LISTENER_API_VERSION = 2

    # RFDS-008 evidence -----------------------------------------------------------
    def _resolve_alias_for_evidence(self, arguments: Mapping[str, Any]) -> str:
        """Same resolution order as :meth:`_session`, but never raises: an
        alias that doesn't have a live session yet (e.g. mid-``Open N83624 *
        Connection``) is a perfectly normal case here."""
        alias = arguments.get("alias")
        if alias:
            try:
                return self._normalize_alias(str(alias))
            except ValidationError:
                return "default"
        if self._active_alias:
            return self._active_alias
        return "default"

    def _ensure_evidence_run(self, alias: str, *, execution_mode: str = "REAL_HARDWARE") -> Any:
        """Get-or-create ``alias``'s evidence run. ``execution_mode`` only takes
        effect on first creation (an already-open alias's run keeps whatever
        mode it was created with, e.g. it isn't overwritten by an unrelated
        later call resolving to the same alias with a different capability)."""
        run = self._evidence_runs.get(alias)
        if run is None:
            if self._evidence_enabled:
                run = _evidence.EvidenceRun(driver_id="rf_ngi_n83624", activity="session", execution_mode=execution_mode)
            else:
                run = _evidence.NullEvidenceRun()
            self._evidence_runs[alias] = run
        return run

    def _finalize_closed_sessions(self, aliases_before: set[str], status: str = "PASS") -> None:
        """Finalize (write run_summary.json/evidence_manifest.json for) every
        alias present in ``aliases_before`` but no longer in ``self._sessions``
        — i.e. whatever this call actually closed. Deliberately a before/after
        diff rather than "alias not in self._sessions", since an alias that
        never had a session yet (e.g. a query before any Connect) would
        otherwise look identically 'closed' and get wrongly finalized."""
        closed_aliases = aliases_before - set(self._sessions)
        for alias in closed_aliases:
            run = self._evidence_runs.pop(alias, None)
            if run is not None:
                run.finalize(status=status)

    def _finalize_remaining_evidence_runs(self, status: str = "PASS") -> None:
        """Finalize every evidence run still open, whatever its alias's state.

        :meth:`_finalize_closed_sessions` only finalizes aliases that *had* a
        session and lost it, so a run created for an alias that never got one
        — any keyword called before ``Open N83624 * Connection``, e.g. a query
        or ``Close All N83624 Connections`` on an empty registry — was never
        finalized. That left an evidence directory on disk holding
        ``environment.json`` and ``events/`` but no ``run_summary.json``,
        ``evidence_manifest.json`` or ``integrity/checksums.sha256``: an
        unverifiable, permanently incomplete RFDS-008 record.

        Runs still bound to a live session are finalized here too, so evidence
        is complete even when ``auto_close_on_suite_end`` is false and the
        caller never closes its connections. ``finalize`` is idempotent, so
        anything already finalized is unaffected.
        """
        for alias in list(self._evidence_runs):
            run = self._evidence_runs.pop(alias, None)
            if run is None:
                continue
            try:
                # A run that recorded an error is never a blanket PASS, whatever
                # the caller's default -- each alias is judged on its own record.
                run_status = "FAIL" if getattr(run, "has_errors", False) else status
                run.finalize(status=run_status)
            except Exception as exc:  # evidence must never mask a test result
                logger.error(f"Finalizing N83624 evidence run for '{alias}' failed: {exc}")

    # Robot listener -------------------------------------------------------------
    def _end_suite(self, name: str, attributes: Mapping[str, Any]) -> None:
        if self.auto_close_on_suite_end:
            try:
                self.close_all_n83624_connections()
            except Exception as exc:  # listener cleanup must not hide test failures
                logger.error(f"Automatic N83624 suite cleanup failed: {exc}")
        # Unconditional: auto_close_on_suite_end governs closing *connections*,
        # never whether the evidence record is left complete on disk.
        self._finalize_remaining_evidence_runs()

    def _close(self) -> None:
        try:
            self.close_all_n83624_connections()
        except Exception as exc:
            logger.error(f"Automatic N83624 library cleanup failed: {exc}")
        self._finalize_remaining_evidence_runs()

    # Connection management -----------------------------------------------------
    @keyword("Open N83624 TCP Connection")
    @_evidenced
    def open_n83624_tcp_connection(
        self,
        alias: str = "default",
        host: str | None = None,
        port: int | str | None = None,
        timeout: float | str | None = None,
        max_voltage_v: float | str | None = None,
        max_current_ma: float | str | None = None,
        max_resistance_mohm: float | str | None = None,
        max_power_mw: float | str | None = None,
        safe_shutdown: bool | str = True,
        verify_identity: bool | str = True,
        allow_raw_scpi: bool | str = False,
        audit_log_path: str | None = None,
    ) -> str:
        """Open a TCP session and make it active.

        The documented N83624 defaults are host ``192.168.0.123`` and port ``7000``.
        Hardware-specific voltage/current limits should be supplied before output use.
        """
        host = host or self.default_host
        port_value = self.default_port if port is None else self._as_int(port, "port")
        timeout_value = self.default_timeout if timeout is None else self._as_float(timeout, "timeout")
        limits = self._make_limits(max_voltage_v, max_current_ma, max_resistance_mohm, max_power_mw)
        policy = self._make_policy(safe_shutdown, verify_identity)
        driver = N83624CellSimulator.tcp(
            host=str(host),
            port=port_value,
            timeout=timeout_value,
            limits=limits,
            safety_policy=policy,
        )
        return self._register_and_connect(
            alias,
            driver,
            safe_shutdown=safe_shutdown,
            allow_raw_scpi=allow_raw_scpi,
            audit_log_path=audit_log_path,
        )

    @keyword("Open N83624 UDP Connection")
    @_evidenced
    def open_n83624_udp_connection(
        self,
        alias: str = "default",
        host: str | None = None,
        port: int | str = 7000,
        timeout: float | str | None = None,
        max_voltage_v: float | str | None = None,
        max_current_ma: float | str | None = None,
        safe_shutdown: bool | str = True,
        verify_identity: bool | str = True,
        allow_raw_scpi: bool | str = False,
        audit_log_path: str | None = None,
    ) -> str:
        """Open a UDP session. Prefer TCP for safety-critical control."""
        host = host or self.default_host
        timeout_value = self.default_timeout if timeout is None else self._as_float(timeout, "timeout")
        limits = self._make_limits(max_voltage_v, max_current_ma, None, None)
        policy = self._make_policy(safe_shutdown, verify_identity)
        driver = N83624CellSimulator.udp(
            host=str(host),
            port=self._as_int(port, "port"),
            timeout=timeout_value,
            limits=limits,
            safety_policy=policy,
        )
        return self._register_and_connect(
            alias,
            driver,
            safe_shutdown=safe_shutdown,
            allow_raw_scpi=allow_raw_scpi,
            audit_log_path=audit_log_path,
        )

    @keyword("Open N83624 Channel UDP Connection")
    @_evidenced
    def open_n83624_channel_udp_connection(
        self,
        alias: str,
        host: str,
        channel: int | str,
        timeout: float | str | None = None,
        max_voltage_v: float | str | None = None,
        max_current_ma: float | str | None = None,
        safe_shutdown: bool | str = True,
        verify_identity: bool | str = True,
        allow_raw_scpi: bool | str = False,
        audit_log_path: str | None = None,
    ) -> str:
        """Open channel-specific UDP port 7001..7024."""
        channel_value = self._channel(channel)
        timeout_value = self.default_timeout if timeout is None else self._as_float(timeout, "timeout")
        limits = self._make_limits(max_voltage_v, max_current_ma, None, None)
        policy = self._make_policy(safe_shutdown, verify_identity)
        driver = N83624CellSimulator.udp_channel(
            host=str(host),
            channel=channel_value,
            timeout=timeout_value,
            limits=limits,
            safety_policy=policy,
        )
        return self._register_and_connect(
            alias,
            driver,
            safe_shutdown=safe_shutdown,
            allow_raw_scpi=allow_raw_scpi,
            audit_log_path=audit_log_path,
        )

    @keyword("Open N83624 Serial Connection")
    @_evidenced
    def open_n83624_serial_connection(
        self,
        alias: str,
        serial_port: str,
        baudrate: int | str = 115200,
        timeout: float | str | None = None,
        max_voltage_v: float | str | None = None,
        max_current_ma: float | str | None = None,
        safe_shutdown: bool | str = True,
        verify_identity: bool | str = True,
        allow_raw_scpi: bool | str = False,
        audit_log_path: str | None = None,
    ) -> str:
        """Open an RS232 session."""
        timeout_value = self.default_timeout if timeout is None else self._as_float(timeout, "timeout")
        limits = self._make_limits(max_voltage_v, max_current_ma, None, None)
        policy = self._make_policy(safe_shutdown, verify_identity)
        driver = N83624CellSimulator.serial(
            port=str(serial_port),
            baudrate=self._as_int(baudrate, "baudrate"),
            timeout=timeout_value,
            limits=limits,
            safety_policy=policy,
        )
        return self._register_and_connect(
            alias,
            driver,
            safe_shutdown=safe_shutdown,
            allow_raw_scpi=allow_raw_scpi,
            audit_log_path=audit_log_path,
        )

    @keyword("Open N83624 Emulator")
    @_evidenced
    def open_n83624_emulator(
        self,
        alias: str = "emulator",
        max_voltage_v: float | str = 5.0,
        max_current_ma: float | str = 1000.0,
        safe_shutdown: bool | str = True,
        allow_raw_scpi: bool | str = True,
        audit_log_path: str | None = None,
    ) -> str:
        """Open the deterministic in-process emulator for tests and examples."""
        emulator = SimpleN83624Emulator()
        limits = self._make_limits(max_voltage_v, max_current_ma, 1_000_000.0, 10_000.0)
        policy = self._make_policy(safe_shutdown, True)
        driver = N83624CellSimulator(emulator, limits=limits, safety_policy=policy)
        return self._register_and_connect(
            alias,
            driver,
            safe_shutdown=safe_shutdown,
            allow_raw_scpi=allow_raw_scpi,
            audit_log_path=audit_log_path,
            emulator=emulator,
        )

    @keyword("Switch N83624 Connection")
    @_evidenced
    def switch_n83624_connection(self, alias: str) -> str:
        """Select the active named session."""
        normalized = self._normalize_alias(alias)
        if normalized not in self._sessions:
            raise SessionStateError(f"Unknown N83624 connection alias: {alias!r}")
        self._active_alias = normalized
        self._audit("switch_connection", alias=normalized)
        return normalized

    @keyword("Get Active N83624 Connection")
    @_evidenced
    def get_active_n83624_connection(self) -> str:
        """Return the active alias."""
        return self._session().alias

    @keyword("List N83624 Connections")
    @_evidenced
    def list_n83624_connections(self) -> list[str]:
        """Return all open aliases."""
        return sorted(self._sessions)

    @keyword("Close N83624 Connection")
    @_evidenced
    def close_n83624_connection(self, alias: str | None = None) -> None:
        """Safely close one session and remove it from the registry."""
        session = self._session(alias)
        error: BaseException | None = None
        try:
            if session.safe_shutdown and session.driver.transport.is_open():
                try:
                    session.driver.all_outputs_off()
                except BaseException as exc:
                    error = exc
                    logger.error(f"N83624 output-off cleanup for {session.alias!r} reported: {exc}")
            session.armed_channels.clear()
            try:
                session.driver.close()
            except BaseException as exc:
                error = error or exc
        finally:
            self._audit_for(session, "close_connection", error=str(error) if error else None)
            self._sessions.pop(session.alias, None)
            if self._active_alias == session.alias:
                self._active_alias = next(iter(self._sessions), None)
        if error is not None:
            raise error

    @keyword("Close All N83624 Connections")
    @_evidenced
    def close_all_n83624_connections(self) -> None:
        """Close all sessions, attempting every session even after failures."""
        errors: list[str] = []
        for alias in list(self._sessions):
            try:
                self.close_n83624_connection(alias)
            except Exception as exc:
                errors.append(f"{alias}: {type(exc).__name__}: {exc}")
        if errors:
            raise SafetyError("One or more N83624 sessions failed safe close: " + "; ".join(errors))

    @keyword("Identify N83624")
    @_evidenced
    def identify_n83624(self, alias: str | None = None) -> str:
        """Return ``*IDN?`` response."""
        session = self._session(alias)
        value = session.driver.identify()
        self._audit_for(session, "identify", response=value)
        return value

    # ------------------------------------------------------------------
    # RFDS-002 mandatory universal keywords
    #
    # Thin, idempotent wrappers over the device-specific keywords above, kept
    # for generic/cross-driver tooling that expects the RFDS canonical names.
    # ``Connect`` defaults to a TCP session; use the device-specific ``Open
    # N83624 ...`` keywords for UDP, serial, or emulator sessions.
    # ------------------------------------------------------------------
    @staticmethod
    def _resource_host(driver: N83624CellSimulator) -> Any:
        transport = driver.transport
        return getattr(transport, "host", None) or getattr(transport, "port", None) or "emulator"

    def _resource_of(self, driver: N83624CellSimulator) -> str:
        transport = driver.transport
        host = getattr(transport, "host", None)
        port = getattr(transport, "port", None)
        if host and port:
            return f"{host}:{port}"
        if port:
            return str(port)
        return "emulator"

    def _connection_state(self, session: _Session) -> dict[str, Any]:
        """Build the RFDS-002 Section 12.1 normalized connection-state dictionary."""
        driver = session.driver
        is_open = driver.transport.is_open()
        identity_str = driver.idn if is_open else None
        return {
            "alias": session.alias,
            "resource": self._resource_of(driver),
            "connected": is_open,
            "communication_ok": identity_str is not None,
            "transport": type(driver.transport).__name__,
            "identity": identity_str,
            "timeout_s": getattr(driver.transport, "timeout", None),
            "state": "connected" if is_open else "disconnected",
        }

    @keyword("Connect")
    @_evidenced
    def connect(
        self,
        resource: str | None = None,
        alias: str = "default",
        timeout_s: float | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """RFDS-002 generic connect. Defaults to a TCP session using ``resource`` as host
        (see ``Open N83624 TCP Connection``).

        Idempotent when ``alias`` is already connected to the same ``resource``.
        """
        normalized = self._normalize_alias(alias)
        if normalized in self._sessions:
            session = self._sessions[normalized]
            existing_host = self._resource_host(session.driver)
            if resource and str(existing_host) != str(resource):
                raise SessionStateError(
                    f"N83624 alias {normalized!r} is already connected to {existing_host!r}; "
                    f"close it before connecting it to {resource!r}."
                )
            return self._connection_state(session)
        connect_kwargs: dict[str, Any] = dict(options)
        if timeout_s is not None:
            connect_kwargs.setdefault("timeout", timeout_s)
        self.open_n83624_tcp_connection(alias=alias, host=resource, **connect_kwargs)
        return self._connection_state(self._sessions[normalized])

    @keyword("Disconnect")
    @_evidenced
    def disconnect(self, alias: str | None = None) -> None:
        """RFDS-002 generic disconnect. Idempotent: succeeds even if already disconnected."""
        normalized = self._active_alias if alias is None or str(alias).strip() == "" else self._normalize_alias(alias)
        if normalized is None or normalized not in self._sessions:
            return
        self.close_n83624_connection(normalized)

    @keyword("Is Connected")
    @_evidenced
    def is_connected(self, alias: str | None = None) -> bool:
        """Return whether ``alias`` (or the active session) is connected."""
        normalized = self._active_alias if alias is None or str(alias).strip() == "" else self._normalize_alias(alias)
        if normalized is None or normalized not in self._sessions:
            return False
        return self._sessions[normalized].driver.transport.is_open()

    @keyword("Get Connection State")
    @_evidenced
    def get_connection_state(self, alias: str | None = None, refresh: bool = False) -> dict[str, Any]:
        """Return the RFDS-002 Section 12.1 normalized connection-state dictionary."""
        normalized = self._active_alias if alias is None or str(alias).strip() == "" else self._normalize_alias(alias)
        if normalized is None or normalized not in self._sessions:
            return {
                "alias": normalized or "default",
                "resource": None,
                "connected": False,
                "communication_ok": False,
                "transport": None,
                "identity": None,
                "timeout_s": None,
                "state": "disconnected",
            }
        session = self._sessions[normalized]
        if self._as_bool(refresh) and session.driver.transport.is_open():
            try:
                session.driver.identify()
            except Exception:
                pass
        return self._connection_state(session)

    @keyword("Check Communication")
    @_evidenced
    def check_communication(self, alias: str | None = None) -> bool:
        """Perform a bounded, non-destructive communication check. Raises on failure."""
        self._session(alias).driver.identify()
        return True

    @keyword("Get Identity")
    @_evidenced
    def get_identity_generic(self, alias: str | None = None, refresh: bool = True) -> str:
        """Return a stable human-readable identity string."""
        del refresh
        return self.identify_n83624(alias)

    # Safety configuration -------------------------------------------------------
    @keyword("Set Channel Safety Limits")
    @_evidenced
    def set_channel_safety_limits(
        self,
        channel: int | str,
        max_voltage_v: float | str,
        max_current_ma: float | str,
        max_resistance_mohm: float | str | None = None,
        max_power_mw: float | str | None = None,
        max_runtime_s: float | str | None = None,
        max_capacity_mah: float | str | None = None,
        alias: str | None = None,
    ) -> dict[str, Any]:
        """Set finite software limits for one channel.

        Existing default limits remain unchanged. The new per-channel limits replace
        any previous per-channel entry.
        """
        session = self._session(alias)
        channel_value = self._channel(channel)
        limits = ChannelLimits(
            max_voltage_v=self._as_float(max_voltage_v, "max_voltage_v"),
            max_current_ma=self._as_float(max_current_ma, "max_current_ma"),
            max_resistance_mohm=self._optional_float(max_resistance_mohm, "max_resistance_mohm"),
            max_power_mw=self._optional_float(max_power_mw, "max_power_mw"),
            max_runtime_s=self._optional_float(max_runtime_s, "max_runtime_s"),
            max_capacity_mah=self._optional_float(max_capacity_mah, "max_capacity_mah"),
        )
        channel_limits = dict(session.driver.limits.channel_limits)
        channel_limits[channel_value] = limits
        session.driver.limits = replace(session.driver.limits, channel_limits=channel_limits)
        session.armed_channels.discard(channel_value)
        result = self._to_robot(limits)
        self._audit_for(session, "set_channel_limits", channel=channel_value, limits=result)
        return result

    @keyword("Get Channel Safety Limits")
    @_evidenced
    def get_channel_safety_limits(self, channel: int | str, alias: str | None = None) -> dict[str, Any]:
        """Return effective channel limits as a dictionary."""
        session = self._session(alias)
        return self._to_robot(session.driver.limits.for_channel(self._channel(channel)))

    @keyword("Arm Channel Output")
    @_evidenced
    def arm_channel_output(
        self,
        channel: int | str,
        confirmation: str = OUTPUT_CONFIRMATION,
        alias: str | None = None,
    ) -> None:
        """Arm one channel for output enable.

        ``confirmation`` must equal ``ENABLE OUTPUT`` exactly and the channel must
        have finite maximum voltage and current limits.
        """
        session = self._session(alias)
        channel_value = self._channel(channel)
        if confirmation != OUTPUT_CONFIRMATION:
            raise SafetyError(f"Output arming requires exact confirmation text: {OUTPUT_CONFIRMATION}")
        limits = session.driver.limits.for_channel(channel_value)
        if not limits.has_output_enable_limits():
            raise SafetyError(
                f"Channel {channel_value} cannot be armed without finite max_voltage_v and max_current_ma"
            )
        session.armed_channels.add(channel_value)
        self._audit_for(session, "arm_output", channel=channel_value)

    @keyword("Disarm Channel Output")
    @_evidenced
    def disarm_channel_output(self, channel: int | str, alias: str | None = None) -> None:
        """Remove output enable permission for one channel."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        session.armed_channels.discard(channel_value)
        self._audit_for(session, "disarm_output", channel=channel_value)

    @keyword("Disarm All Channel Outputs")
    @_evidenced
    def disarm_all_channel_outputs(self, alias: str | None = None) -> None:
        """Remove output enable permission from all channels."""
        session = self._session(alias)
        session.armed_channels.clear()
        self._audit_for(session, "disarm_all_outputs")

    @keyword("Channel Output Should Be Armed")
    @_evidenced
    def channel_output_should_be_armed(self, channel: int | str, alias: str | None = None) -> None:
        """Fail unless the channel is armed."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        if channel_value not in session.armed_channels:
            raise AssertionError(f"N83624 channel {channel_value} is not armed")

    # Output and configuration ---------------------------------------------------
    @keyword("Set Channel Mode")
    @_evidenced
    def set_channel_mode(
        self,
        channel: int | str,
        mode: str | int,
        output_off_first: bool | str = True,
        verify: bool | str = True,
        alias: str | None = None,
    ) -> str:
        """Set SOURCE, CHARGE, SOC, or SEQUENCE mode."""
        session = self._session(alias)
        mode_value = self._enum(OutputMode, mode, "mode")
        session.driver.channel(self._channel(channel)).set_mode(
            mode_value,
            output_off_first=self._as_bool(output_off_first),
            verify=self._as_bool(verify),
        )
        self._audit_for(session, "set_mode", channel=self._channel(channel), mode=mode_value.name)
        return mode_value.name

    @keyword("Get Channel Mode")
    @_evidenced
    def get_channel_mode(self, channel: int | str, alias: str | None = None) -> str:
        """Return channel mode name."""
        return self._session(alias).driver.channel(self._channel(channel)).get_mode().name

    @keyword("Configure Source Mode")
    @_evidenced
    def configure_source_mode(
        self,
        channel: int | str,
        voltage_v: float | str,
        current_limit_ma: float | str,
        current_range: str | int = "AUTO",
        output: bool | str = False,
        verify: bool | str = True,
        alias: str | None = None,
    ) -> None:
        """Configure source mode and optionally enable the output."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        output_value = self._as_bool(output)
        if output_value:
            self._require_armed(session, channel_value)
        range_value = self._enum(CurrentRange, current_range, "current_range")
        session.driver.channel(channel_value).configure_source(
            self._as_float(voltage_v, "voltage_v"),
            self._as_float(current_limit_ma, "current_limit_ma"),
            range_value,
            output=output_value,
            verify=self._as_bool(verify),
        )
        self._audit_for(
            session,
            "configure_source",
            channel=channel_value,
            voltage_v=float(voltage_v),
            current_limit_ma=float(current_limit_ma),
            current_range=range_value.name,
            output=output_value,
        )

    @keyword("Configure Charge Mode")
    @_evidenced
    def configure_charge_mode(
        self,
        channel: int | str,
        voltage_v: float | str,
        current_limit_ma: float | str,
        resistance_mohm: float | str,
        output: bool | str = False,
        verify: bool | str = True,
        alias: str | None = None,
    ) -> None:
        """Configure charge mode and optionally enable the output."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        output_value = self._as_bool(output)
        if output_value:
            self._require_armed(session, channel_value)
        session.driver.channel(channel_value).configure_charge(
            self._as_float(voltage_v, "voltage_v"),
            self._as_float(current_limit_ma, "current_limit_ma"),
            self._as_float(resistance_mohm, "resistance_mohm"),
            output=output_value,
            verify=self._as_bool(verify),
        )
        self._audit_for(session, "configure_charge", channel=channel_value, output=output_value)

    @keyword("Configure SOC Profile")
    @_evidenced
    def configure_soc_profile(
        self,
        channel: int | str,
        steps: Any,
        file_number: int | str = 1,
        start_voltage_v: float | str | None = None,
        output: bool | str = False,
        verify: bool | str = True,
        alias: str | None = None,
    ) -> None:
        """Configure SOC profile from a Robot list or JSON list of dictionaries."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        output_value = self._as_bool(output)
        if output_value:
            self._require_armed(session, channel_value)
        parsed_steps = [self._soc_step(item) for item in self._as_sequence(steps, "steps")]
        session.driver.channel(channel_value).configure_soc(
            parsed_steps,
            file_number=self._as_int(file_number, "file_number"),
            start_voltage_v=self._optional_float(start_voltage_v, "start_voltage_v"),
            output=output_value,
            verify=self._as_bool(verify),
        )
        self._audit_for(session, "configure_soc", channel=channel_value, steps=len(parsed_steps), output=output_value)

    @keyword("Configure Sequence Profile")
    @_evidenced
    def configure_sequence_profile(
        self,
        channel: int | str,
        file_number: int | str,
        steps: Any,
        file_cycle: int | str = 1,
        output: bool | str = False,
        verify: bool | str = True,
        alias: str | None = None,
    ) -> None:
        """Configure sequence profile from a Robot list or JSON list of dictionaries."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        output_value = self._as_bool(output)
        if output_value:
            self._require_armed(session, channel_value)
        parsed_steps = [self._sequence_step(item) for item in self._as_sequence(steps, "steps")]
        session.driver.channel(channel_value).configure_sequence(
            self._as_int(file_number, "file_number"),
            parsed_steps,
            file_cycle=self._as_int(file_cycle, "file_cycle"),
            output=output_value,
            verify=self._as_bool(verify),
        )
        self._audit_for(
            session,
            "configure_sequence",
            channel=channel_value,
            steps=len(parsed_steps),
            output=output_value,
        )

    @keyword("Enable Channel Output")
    @_evidenced
    def enable_channel_output(self, channel: int | str, alias: str | None = None) -> None:
        """Enable one armed channel output."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        self._require_armed(session, channel_value)
        session.driver.channel(channel_value).output_on()
        self._audit_for(session, "output_on", channel=channel_value)

    @keyword("Disable Channel Output")
    @_evidenced
    def disable_channel_output(self, channel: int | str, alias: str | None = None) -> None:
        """Disable one output. This operation never requires arming."""
        session = self._session(alias)
        channel_value = self._channel(channel)
        session.driver.channel(channel_value).output_off()
        self._audit_for(session, "output_off", channel=channel_value)

    @keyword("All N83624 Outputs Off")
    @_evidenced
    def all_n83624_outputs_off(self, alias: str | None = None, disarm: bool | str = True) -> None:
        """Attempt to disable all 24 outputs."""
        session = self._session(alias)
        session.driver.all_outputs_off()
        if self._as_bool(disarm):
            session.armed_channels.clear()
        self._audit_for(session, "all_outputs_off", disarm=self._as_bool(disarm))

    @keyword("Get Channel Output State")
    @_evidenced
    def get_channel_output_state(self, channel: int | str, alias: str | None = None) -> bool:
        """Return true when output is enabled."""
        return self._session(alias).driver.channel(self._channel(channel)).get_output()

    @keyword("Channel Output Should Be On")
    @_evidenced
    def channel_output_should_be_on(self, channel: int | str, alias: str | None = None) -> None:
        """Fail unless output is on."""
        if not self.get_channel_output_state(channel, alias):
            raise AssertionError(f"N83624 channel {self._channel(channel)} output is OFF")

    @keyword("Channel Output Should Be Off")
    @_evidenced
    def channel_output_should_be_off(self, channel: int | str, alias: str | None = None) -> None:
        """Fail unless output is off."""
        if self.get_channel_output_state(channel, alias):
            raise AssertionError(f"N83624 channel {self._channel(channel)} output is ON")

    # Measurements and assertions -----------------------------------------------
    @keyword("Measure Channel Voltage")
    @_evidenced
    def measure_channel_voltage(self, channel: int | str, alias: str | None = None) -> float:
        """Return channel voltage in volts."""
        return self._session(alias).driver.channel(self._channel(channel)).measure_voltage_v()

    @keyword("Measure Channel Current")
    @_evidenced
    def measure_channel_current(self, channel: int | str, alias: str | None = None) -> float:
        """Return channel current in milliamperes."""
        return self._session(alias).driver.channel(self._channel(channel)).measure_current_ma()

    @keyword("Measure Channel Power")
    @_evidenced
    def measure_channel_power(self, channel: int | str, alias: str | None = None) -> float:
        """Return channel power in watts."""
        return self._session(alias).driver.channel(self._channel(channel)).measure_power_w()

    @keyword("Measure Channel Resistance")
    @_evidenced
    def measure_channel_resistance(self, channel: int | str, alias: str | None = None) -> float:
        """Return channel resistance in milliohms."""
        return self._session(alias).driver.channel(self._channel(channel)).measure_resistance_mohm()

    @keyword("Measure Channel Capacity")
    @_evidenced
    def measure_channel_capacity(self, channel: int | str, alias: str | None = None) -> float:
        """Return channel capacity in mAh."""
        return self._session(alias).driver.channel(self._channel(channel)).measure_capacity_mah()

    @keyword("Measure Channel")
    @_evidenced
    def measure_channel(self, channel: int | str, alias: str | None = None) -> dict[str, Any]:
        """Return all supported channel measurements as a dictionary."""
        measurement = self._session(alias).driver.channel(self._channel(channel)).measure_all()
        return self._to_robot(measurement)

    @keyword("Measure Voltage Channels")
    @_evidenced
    def measure_voltage_channels(self, channels: Any, alias: str | None = None) -> dict[int, float]:
        """Measure multiple channels. ``channels`` may be a Robot list or CSV string."""
        values = [self._channel(item) for item in self._as_channel_sequence(channels)]
        return self._session(alias).driver.measure_voltage_channels(values)

    @keyword("Channel Voltage Should Be Within")
    @_evidenced
    def channel_voltage_should_be_within(
        self,
        channel: int | str,
        expected_v: float | str,
        tolerance_v: float | str,
        alias: str | None = None,
    ) -> float:
        """Measure voltage and fail when absolute error exceeds tolerance."""
        actual = self.measure_channel_voltage(channel, alias)
        self._assert_within(actual, expected_v, tolerance_v, "voltage", "V")
        return actual

    @keyword("Channel Current Should Be Within")
    @_evidenced
    def channel_current_should_be_within(
        self,
        channel: int | str,
        expected_ma: float | str,
        tolerance_ma: float | str,
        alias: str | None = None,
    ) -> float:
        """Measure current and fail when absolute error exceeds tolerance."""
        actual = self.measure_channel_current(channel, alias)
        self._assert_within(actual, expected_ma, tolerance_ma, "current", "mA")
        return actual

    @keyword("Wait Until Channel Voltage Is Within")
    @_evidenced
    def wait_until_channel_voltage_is_within(
        self,
        channel: int | str,
        expected_v: float | str,
        tolerance_v: float | str,
        timeout: float | str = 5.0,
        interval: float | str = 0.1,
        alias: str | None = None,
    ) -> float:
        """Poll voltage until it is within tolerance or timeout expires."""
        return self._wait_within(
            lambda: self.measure_channel_voltage(channel, alias),
            expected_v,
            tolerance_v,
            timeout,
            interval,
            f"channel {self._channel(channel)} voltage",
            "V",
        )

    @keyword("Wait Until Channel Current Is Within")
    @_evidenced
    def wait_until_channel_current_is_within(
        self,
        channel: int | str,
        expected_ma: float | str,
        tolerance_ma: float | str,
        timeout: float | str = 5.0,
        interval: float | str = 0.1,
        alias: str | None = None,
    ) -> float:
        """Poll current until it is within tolerance or timeout expires."""
        return self._wait_within(
            lambda: self.measure_channel_current(channel, alias),
            expected_ma,
            tolerance_ma,
            timeout,
            interval,
            f"channel {self._channel(channel)} current",
            "mA",
        )

    @keyword("Get Channel Status")
    @_evidenced
    def get_channel_status(self, channel: int | str, alias: str | None = None) -> dict[str, Any]:
        """Return decoded status bits."""
        return self._to_robot(self._session(alias).driver.channel(self._channel(channel)).get_status())

    @keyword("Get Channel Event")
    @_evidenced
    def get_channel_event(self, channel: int | str, alias: str | None = None) -> dict[str, Any]:
        """Return decoded event bits."""
        return self._to_robot(self._session(alias).driver.channel(self._channel(channel)).get_event())

    @keyword("Get Channel Configuration")
    @_evidenced
    def get_channel_configuration(self, channel: int | str, alias: str | None = None) -> dict[str, Any]:
        """Return a typed configuration snapshot as a Robot dictionary."""
        return self._to_robot(
            self._session(alias).driver.channel(self._channel(channel)).read_channel_configuration()
        )

    # Protection and acquisition -------------------------------------------------
    @keyword("Set Channel Protection Limits")
    @_evidenced
    def set_channel_protection_limits(
        self,
        channel: int | str,
        ocp_current_ma: float | str,
        ovp_voltage_v: float | str,
        opp_power_mw: float | str,
        alias: str | None = None,
    ) -> None:
        """Set OCP, OVP, and OPP thresholds."""
        session = self._session(alias)
        proxy = session.driver.channel(self._channel(channel))
        proxy.set_ocp_current_ma(self._as_float(ocp_current_ma, "ocp_current_ma"))
        proxy.set_ovp_voltage_v(self._as_float(ovp_voltage_v, "ovp_voltage_v"))
        proxy.set_opp_power_mw(self._as_float(opp_power_mw, "opp_power_mw"))
        self._audit_for(session, "set_protection", channel=self._channel(channel))

    @keyword("Set Channel Capture Rate")
    @_evidenced
    def set_channel_capture_rate(
        self,
        channel: int | str,
        rate: str | int,
        alias: str | None = None,
    ) -> str:
        """Set FAST_10MS, MEDIUM_120MS, or SLOW_480MS capture rate."""
        rate_value = self._enum(CaptureRate, rate, "capture rate")
        self._session(alias).driver.channel(self._channel(channel)).set_capture_rate(rate_value)
        return rate_value.name

    @keyword("Get Channel Capture Rate")
    @_evidenced
    def get_channel_capture_rate(self, channel: int | str, alias: str | None = None) -> str:
        """Return capture rate name."""
        return self._session(alias).driver.channel(self._channel(channel)).get_capture_rate().name

    # Heartbeat and recovery -----------------------------------------------------
    @keyword("Start N83624 Heartbeat")
    @_evidenced
    def start_n83624_heartbeat(
        self,
        interval_s: float | str = 10.0,
        fail_after: int | str = 3,
        query: str = "*IDN?",
        alias: str | None = None,
    ) -> None:
        """Start background communication supervision."""
        session = self._session(alias)
        session.driver.start_heartbeat(
            HeartbeatConfig(
                interval_s=self._as_float(interval_s, "interval_s"),
                fail_after=self._as_int(fail_after, "fail_after"),
                query=str(query),
            )
        )
        self._audit_for(session, "heartbeat_start", interval_s=float(interval_s), fail_after=int(fail_after))

    @keyword("Stop N83624 Heartbeat")
    @_evidenced
    def stop_n83624_heartbeat(self, alias: str | None = None) -> None:
        """Stop background heartbeat."""
        session = self._session(alias)
        session.driver.stop_heartbeat()
        self._audit_for(session, "heartbeat_stop")

    @keyword("Get N83624 Communication Health")
    @_evidenced
    def get_n83624_communication_health(self, alias: str | None = None) -> dict[str, Any]:
        """Return session state and latest communication observation."""
        session = self._session(alias)
        return {
            "alias": session.alias,
            "state": session.driver.state.value,
            "idn": session.driver.idn,
            "observation": self._to_robot(session.driver.get_communication_observation()),
        }

    @keyword("Recover N83624 Connection")
    @_evidenced
    def recover_n83624_connection(self, alias: str | None = None) -> None:
        """Attempt transport reconnect using the configured recovery policy."""
        session = self._session(alias)
        session.driver.recover()
        session.armed_channels.clear()
        self._audit_for(session, "recover")

    # Raw SCPI -------------------------------------------------------------------
    @keyword("Enable Raw SCPI")
    @_evidenced
    def enable_raw_scpi(
        self,
        confirmation: str,
        alias: str | None = None,
    ) -> None:
        """Enable raw SCPI for a session using exact confirmation text."""
        session = self._session(alias)
        if confirmation != RAW_SCPI_CONFIRMATION:
            raise SafetyError(f"Raw SCPI enable requires exact confirmation text: {RAW_SCPI_CONFIRMATION}")
        session.allow_raw_scpi = True
        self._audit_for(session, "raw_scpi_enabled")

    @keyword("Raw SCPI Query")
    @_evidenced
    def raw_scpi_query(self, command: str, alias: str | None = None) -> str:
        """Send a raw SCPI query when explicitly enabled."""
        session = self._session(alias)
        self._require_raw_scpi(session)
        response = session.driver.query(str(command))
        self._audit_for(session, "raw_query", command=command, response=response)
        return response

    @keyword("Raw SCPI Write")
    @_evidenced
    def raw_scpi_write(self, command: str, alias: str | None = None) -> None:
        """Send a raw SCPI write when explicitly enabled.

        Raw writes bypass typed validation and the output arming gate. Use only for
        diagnostics or commands not yet represented by the library.
        """
        session = self._session(alias)
        self._require_raw_scpi(session)
        session.driver.write(str(command))
        self._audit_for(session, "raw_write", command=command)

    # Emulator support -----------------------------------------------------------
    @keyword("Set Emulator Channel Measurement")
    @_evidenced
    def set_emulator_channel_measurement(
        self,
        channel: int | str,
        voltage_v: float | str | None = None,
        current_ma: float | str | None = None,
        power_w: float | str | None = None,
        capacity_mah: float | str | None = None,
        resistance_mohm: float | str | None = None,
        alias: str | None = None,
    ) -> None:
        """Set deterministic emulator readback values for offline Robot tests."""
        session = self._session(alias)
        if session.emulator is None:
            raise SessionStateError("Active N83624 session is not an emulator")
        channel_value = self._channel(channel)
        values = {
            "VOLTage": voltage_v,
            "CURRent": current_ma,
            "POWer": power_w,
            "MAH": capacity_mah,
            "Res": resistance_mohm,
        }
        for leaf, value in values.items():
            if value is not None and str(value).strip() != "":
                session.emulator.state[f"MEASure{channel_value}:{leaf}"] = self._as_float(value, leaf)
        self._audit_for(session, "set_emulator_measurement", channel=channel_value)

    @keyword("Get Emulator Command Log")
    @_evidenced
    def get_emulator_command_log(self, alias: str | None = None) -> list[str]:
        """Return all commands recorded by the active emulator."""
        session = self._session(alias)
        if session.emulator is None:
            raise SessionStateError("Active N83624 session is not an emulator")
        return list(session.emulator.all_commands)

    @keyword("Export Diagnostic Bundle")
    @_evidenced
    def export_diagnostic_bundle(self, alias: str | None = None, destination: str | None = None) -> str | None:
        """Zip ``alias`` (or the active session)'s RFDS-008 evidence run for troubleshooting.

        Works whether or not the session is still connected — closing it
        finalizes the run for the last time, this can be called before or
        after that. Returns the archive path, or ``None`` when
        ``evidence_enabled=False`` was passed to this library instance.
        """
        resolved_alias = self._resolve_alias_for_evidence({"alias": alias})
        run = self._ensure_evidence_run(resolved_alias)
        return run.export_diagnostic_bundle(None if not destination else str(destination))

    # Helpers --------------------------------------------------------------------
    def _register_and_connect(
        self,
        alias: str,
        driver: N83624CellSimulator,
        *,
        safe_shutdown: bool | str,
        allow_raw_scpi: bool | str,
        audit_log_path: str | None,
        emulator: SimpleN83624Emulator | None = None,
    ) -> str:
        normalized = self._normalize_alias(alias)
        if normalized in self._sessions:
            raise SessionStateError(f"N83624 connection alias already exists: {normalized!r}")
        session = _Session(
            alias=normalized,
            driver=driver,
            safe_shutdown=self._as_bool(safe_shutdown),
            allow_raw_scpi=self._as_bool(allow_raw_scpi),
            audit_log_path=Path(audit_log_path).expanduser().resolve() if audit_log_path else None,
            armed_channels=set(),
            emulator=emulator,
        )
        # This alias's evidence run already exists by now (created by the
        # @_evidenced wrapper around whichever Open N83624 * Connection
        # keyword called us) — wire the core driver's protocol_observer hook
        # to it so every SCPI write/query this session makes, starting with
        # driver.connect()'s own identity query, is traced.
        evidence_run = self._ensure_evidence_run(normalized)
        driver.protocol_observer = lambda direction, text: evidence_run.log_protocol(
            direction, "scpi", text, session_alias=normalized
        )
        try:
            driver.connect()
        except Exception:
            try:
                driver.transport.close()
            finally:
                raise
        self._sessions[normalized] = session
        self._active_alias = normalized
        evidence_run.record_device_identity(
            manufacturer="NGI",
            model="N83624",
            identity_response=driver.idn,
            transport_type=type(driver.transport).__name__,
            resource=self._resource_of(driver),
        )
        self._audit_for(session, "open_connection", idn=driver.idn, safe_shutdown=session.safe_shutdown)
        logger.info(f"Opened N83624 connection {normalized!r}: {driver.idn or 'identity check disabled'}")
        return normalized

    def _session(self, alias: str | None = None) -> _Session:
        normalized = self._active_alias if alias is None or str(alias).strip() == "" else self._normalize_alias(alias)
        if normalized is None:
            raise SessionStateError("No active N83624 connection")
        try:
            return self._sessions[normalized]
        except KeyError as exc:
            raise SessionStateError(f"Unknown N83624 connection alias: {normalized!r}") from exc

    @staticmethod
    def _normalize_alias(alias: str) -> str:
        normalized = str(alias).strip()
        if not normalized:
            raise ValidationError("Connection alias must not be empty")
        return normalized

    @staticmethod
    def _make_policy(safe_shutdown: bool | str, verify_identity: bool | str) -> DriverSafetyPolicy:
        return DriverSafetyPolicy(
            require_limits_before_output_on=True,
            output_off_on_close=False,  # wrapper performs best-effort all-channel cleanup once
            output_off_on_exception=True,
            fault_simulation_enabled=False,
            require_interlock_for_output_on=False,  # wrapper's explicit arming gate is enforced instead
            require_interlock_for_fault_simulation=True,
            require_status_check_after_setters=True,
            require_identity_check_on_connect=NGI_N83624._as_bool(verify_identity),
        )

    @staticmethod
    def _make_limits(
        max_voltage_v: float | str | None,
        max_current_ma: float | str | None,
        max_resistance_mohm: float | str | None,
        max_power_mw: float | str | None,
    ) -> InstrumentLimits:
        return InstrumentLimits(
            model_name="NGI N83624 - verify exact hardware ratings",
            default_channel_limits=ChannelLimits(
                max_voltage_v=NGI_N83624._optional_float(max_voltage_v, "max_voltage_v"),
                max_current_ma=NGI_N83624._optional_float(max_current_ma, "max_current_ma"),
                max_resistance_mohm=NGI_N83624._optional_float(
                    max_resistance_mohm, "max_resistance_mohm"
                ),
                max_power_mw=NGI_N83624._optional_float(max_power_mw, "max_power_mw"),
            ),
        )

    @staticmethod
    def _require_armed(session: _Session, channel: int) -> None:
        if channel not in session.armed_channels:
            raise SafetyError(
                f"N83624 channel {channel} is not armed. Call 'Arm Channel Output' with "
                f"confirmation '{OUTPUT_CONFIRMATION}' after configuring verified limits."
            )

    @staticmethod
    def _require_raw_scpi(session: _Session) -> None:
        if not session.allow_raw_scpi:
            raise SafetyError(
                f"Raw SCPI is disabled for alias {session.alias!r}. Use 'Enable Raw SCPI' with "
                f"confirmation '{RAW_SCPI_CONFIRMATION}'."
            )

    @staticmethod
    def _channel(value: int | str) -> int:
        result = NGI_N83624._as_int(value, "channel")
        if not 1 <= result <= 24:
            raise ValidationError(f"channel must be in range 1..24; got {result}")
        return result

    @staticmethod
    def _as_bool(value: bool | str | int) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"true", "yes", "on", "1", "${true}"}:
            return True
        if text in {"false", "no", "off", "0", "${false}", "", "none"}:
            return False
        raise ValidationError(f"Expected boolean value; got {value!r}")

    @staticmethod
    def _as_int(value: int | str, name: str) -> int:
        if isinstance(value, bool):
            raise ValidationError(f"{name} must be an integer, not boolean")
        try:
            result = int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name} must be an integer; got {value!r}") from exc
        return result

    @staticmethod
    def _as_float(value: float | int | str, name: str) -> float:
        if isinstance(value, bool):
            raise ValidationError(f"{name} must be numeric, not boolean")
        try:
            result = float(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"{name} must be numeric; got {value!r}") from exc
        if not math.isfinite(result):
            raise ValidationError(f"{name} must be finite; got {value!r}")
        return result

    @staticmethod
    def _optional_float(value: float | int | str | None, name: str) -> float | None:
        if value is None or str(value).strip().lower() in {"", "none", "${none}"}:
            return None
        return NGI_N83624._as_float(value, name)

    @staticmethod
    def _enum(enum_type: type[Enum], value: str | int | Enum, name: str) -> Any:
        if isinstance(value, enum_type):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValidationError(f"{name} must not be empty")
            try:
                return enum_type[text.upper()]
            except KeyError:
                pass
            try:
                return enum_type(int(text))
            except (ValueError, TypeError):
                pass
        else:
            try:
                return enum_type(int(value))
            except (ValueError, TypeError):
                pass
        choices = ", ".join(f"{item.name}({item.value})" for item in enum_type)
        raise ValidationError(f"Invalid {name} {value!r}; allowed values: {choices}")

    @staticmethod
    def _as_sequence(value: Any, name: str) -> Sequence[Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{name} must be a Robot list or JSON list: {exc}") from exc
        if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
            raise ValidationError(f"{name} must be a sequence; got {type(value).__name__}")
        if not value:
            raise ValidationError(f"{name} must not be empty")
        return value

    @staticmethod
    def _as_channel_sequence(value: Any) -> list[Any]:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValidationError(f"Invalid channel JSON list: {exc}") from exc
                return list(parsed)
            return [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(value, Iterable):
            return list(value)
        raise ValidationError(f"channels must be a list or CSV string; got {type(value).__name__}")

    @staticmethod
    def _as_mapping(value: Any, name: str) -> Mapping[str, Any]:
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValidationError(f"{name} must be a dictionary or JSON object: {exc}") from exc
        if not isinstance(value, Mapping):
            raise ValidationError(f"{name} must be a mapping; got {type(value).__name__}")
        return value

    @classmethod
    def _soc_step(cls, value: Any) -> SocStep:
        item = cls._as_mapping(value, "SOC step")
        return SocStep(
            capacity_mah=cls._as_float(item["capacity_mah"], "capacity_mah"),
            voltage_v=cls._as_float(item["voltage_v"], "voltage_v"),
            current_limit_ma=cls._as_float(item["current_limit_ma"], "current_limit_ma"),
            resistance_mohm=cls._as_float(item["resistance_mohm"], "resistance_mohm"),
        )

    @classmethod
    def _sequence_step(cls, value: Any) -> SequenceStep:
        item = cls._as_mapping(value, "sequence step")
        return SequenceStep(
            voltage_v=cls._as_float(item["voltage_v"], "voltage_v"),
            current_limit_ma=cls._as_float(item["current_limit_ma"], "current_limit_ma"),
            resistance_mohm=cls._as_float(item["resistance_mohm"], "resistance_mohm"),
            runtime_s=cls._as_float(item["runtime_s"], "runtime_s"),
            link_start=cls._as_int(item.get("link_start", -1), "link_start"),
            link_end=cls._as_int(item.get("link_end", -1), "link_end"),
            link_cycle=cls._as_int(item.get("link_cycle", 0), "link_cycle"),
        )

    @classmethod
    def _to_robot(cls, value: Any) -> Any:
        if isinstance(value, Enum):
            return value.name
        if is_dataclass(value):
            return cls._to_robot(asdict(value))
        if isinstance(value, Mapping):
            return {key: cls._to_robot(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [cls._to_robot(item) for item in value]
        return value

    @classmethod
    def _assert_within(
        cls,
        actual: float,
        expected: float | str,
        tolerance: float | str,
        quantity: str,
        unit: str,
    ) -> None:
        expected_value = cls._as_float(expected, f"expected_{quantity}")
        tolerance_value = cls._as_float(tolerance, f"{quantity}_tolerance")
        if tolerance_value < 0:
            raise ValidationError("tolerance must be non-negative")
        delta = abs(actual - expected_value)
        if delta > tolerance_value:
            raise AssertionError(
                f"N83624 {quantity} {actual:g} {unit} is outside {expected_value:g} ± "
                f"{tolerance_value:g} {unit}; absolute error={delta:g} {unit}"
            )

    @classmethod
    def _wait_within(
        cls,
        measurement: Any,
        expected: float | str,
        tolerance: float | str,
        timeout: float | str,
        interval: float | str,
        label: str,
        unit: str,
    ) -> float:
        expected_value = cls._as_float(expected, "expected")
        tolerance_value = cls._as_float(tolerance, "tolerance")
        timeout_value = cls._as_float(timeout, "timeout")
        interval_value = cls._as_float(interval, "interval")
        if tolerance_value < 0 or timeout_value < 0 or interval_value <= 0:
            raise ValidationError("tolerance and timeout must be non-negative; interval must be positive")
        deadline = time.monotonic() + timeout_value
        last = float("nan")
        while True:
            last = float(measurement())
            if abs(last - expected_value) <= tolerance_value:
                return last
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"Timed out waiting for {label}: last={last:g} {unit}, expected={expected_value:g} "
                    f"± {tolerance_value:g} {unit}, timeout={timeout_value:g} s"
                )
            time.sleep(interval_value)

    def _audit(self, action: str, **details: Any) -> None:
        if self._active_alias and self._active_alias in self._sessions:
            self._audit_for(self._sessions[self._active_alias], action, **details)

    @staticmethod
    def _audit_for(session: _Session, action: str, **details: Any) -> None:
        path = session.audit_log_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "release": RELEASE_VERSION,
            "alias": session.alias,
            "action": action,
            **details,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
