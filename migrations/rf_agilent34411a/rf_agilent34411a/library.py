"""Robot Framework adapter for :mod:`agilent34411a`.

Keeps SCPI construction and validation entirely in the core driver
(task §5.2) — this module only converts arguments/results and manages
named sessions.

Every public keyword is also wrapped with an RFDS-008 evidence operation
record (see ``_instrument_all_keywords`` below and ``evidence.py``) —
arguments, duration, result/failure, and a correlated trace of the actual
SCPI commands/responses exchanged with the instrument, written to
``results/session/rf_agilent34411a/<run>/`` for troubleshooting. See
``docs/logging_and_evidence.md``. Pass ``evidence_enabled=${FALSE}`` to the
``Library`` import to disable it.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from . import evidence as _evidence

try:  # Robot Framework is optional at import time so pytest can run standalone.
    from robot.api import logger as _rf_logger
    from robot.api.deco import keyword, library
except ImportError:  # pragma: no cover

    class _FallbackLogger:
        @staticmethod
        def info(message: str, *_args: Any, **_kwargs: Any) -> None:
            print(message)

        warn = error = debug = info

    _rf_logger = _FallbackLogger()

    def keyword(name: str | None = None, tags: tuple[str, ...] = ()):  # type: ignore[misc]
        def decorate(func):
            func.robot_name = name or func.__name__.replace("_", " ").title()
            func.robot_tags = tags
            return func

        return decorate

    def library(**_kwargs: Any):  # type: ignore[misc]
        return lambda cls: cls


from agilent34411a import Agilent34411A
from agilent34411a.exceptions import Agilent34411AConnectionError, Agilent34411AValidationError


def _as_bool(value: Any, name: str = "value") -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", "", "none"}:
            return False
    raise Agilent34411AValidationError(f"{name} must be a Boolean, got {value!r}")


def _robot_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _robot_value(v) for k, v in asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_robot_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _robot_value(v) for k, v in value.items()}
    return value


def _evidenced(func: Any) -> Any:
    """Wrap one keyword method with an RFDS-008 evidence operation record.

    Resolves the ``alias`` argument (present on almost every keyword here)
    to a concrete session alias for the evidence record's ``session_alias``
    field, falling back to the currently active alias the same way
    ``_resolve_alias`` does. Reads ``self._evidence`` (created lazily by
    ``_ensure_evidence``). Called from ``_instrument_all_keywords`` *after*
    ``@keyword(...)`` has already set ``robot_name`` on ``func``, so
    ``functools.wraps`` copies it onto ``wrapper`` automatically — no
    decoration-order trick needed here (contrast with
    ``rf_phidget_relay/rf_phidget_relay/library.py``, which applies its
    equivalent decorator *before* ``@keyword`` runs and has to read
    ``wrapper.robot_name`` at call time instead).
    """
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(self: Agilent34411ALibrary, *args: Any, **kwargs: Any) -> Any:
        capability = getattr(wrapper, "robot_name", None) or func.__name__.replace("_", " ").title()
        run = self._ensure_evidence()
        bound = signature.bind_partial(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {key: value for key, value in bound.arguments.items() if key != "self"}
        session_alias = self._resolve_alias(arguments.get("alias")) or "default"
        with run.record_operation(capability, arguments=arguments, session_alias=session_alias) as op:
            result = func(self, *args, **kwargs)
            op.set_result(result)
            return result

    return wrapper


def _instrument_all_keywords(cls: type) -> type:
    """Class decorator: wrap every ``@keyword``-decorated method with ``_evidenced``.

    Applied once here rather than annotating each of this library's 148
    keyword methods individually — mechanically identical to per-method
    ``@_evidenced``, just far less error-prone at this keyword count. Runs
    after the class body finishes executing, so every ``@keyword(...)`` call
    inside the class body has already set ``robot_name`` on its method by
    the time this walks ``vars(cls)``.
    """
    for name, value in list(vars(cls).items()):
        if callable(value) and getattr(value, "robot_name", None):
            setattr(cls, name, _evidenced(value))
    return cls


@_instrument_all_keywords
@library(scope="SUITE", version="26.2", auto_keywords=False)
class Agilent34411ALibrary:
    """Robot Framework keywords for the Agilent (Keysight) 34411A digital multimeter.

    The RFDS-002 canonical connection keywords (``Connect``, ``Disconnect``,
    ``Is Connected``, ``Get Connection State``, ``Check Communication``,
    ``Get Identity``) are the primary, documented connection API — see the
    task document, task §7. No hardware is touched on library import.
    """

    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_LIBRARY_VERSION = "26.2"

    def __init__(self, evidence_enabled: Any = True) -> None:
        self._sessions: dict[str, Agilent34411A] = {}
        self._active_alias: str | None = None
        self._evidence_enabled = _as_bool(evidence_enabled, "evidence_enabled")
        self._evidence: Any = None
        self.ROBOT_LIBRARY_LISTENER = self

    def _ensure_evidence(self) -> Any:
        """Lazily create (or return) this library instance's :class:`evidence.EvidenceRun`.

        One run per library instance (this library is ``ROBOT_LIBRARY_SCOPE
        = "SUITE"``), covering every alias/session connected during the
        suite — see ``evidence.py``'s module docstring for why finalization
        happens in ``_end_suite`` rather than in ``Disconnect``.
        """
        if self._evidence is None:
            if self._evidence_enabled:
                self._evidence = _evidence.EvidenceRun(
                    driver_id="rf_agilent34411a", activity="session", execution_mode="NO_HARDWARE"
                )
            else:
                self._evidence = _evidence.NullEvidenceRun()
        return self._evidence

    def _end_suite(self, name: str, attributes: dict[str, Any]) -> None:
        del name, attributes
        for alias in list(self._sessions):
            try:
                self._sessions[alias].close()
            except Exception as exc:  # noqa: BLE001 - cleanup must not hide an earlier suite failure
                _rf_logger.warn(f"Agilent34411A: cleanup for {alias!r} reported: {exc}")  # noqa: G010 - robot.api.logger has no .warning
        self._sessions.clear()
        self._active_alias = None
        if self._evidence is not None:
            self._evidence.finalize(status="PASS")
            self._evidence = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_alias(self, alias: str | None) -> str | None:
        return str(alias) if alias not in (None, "") else self._active_alias

    def _session(self, alias: str | None = None) -> Agilent34411A:
        selected = self._resolve_alias(alias)
        if selected is None:
            raise Agilent34411AConnectionError(
                "no Agilent 34411A connection is active; call 'Connect' first"
            )
        try:
            return self._sessions[selected]
        except KeyError as exc:
            known = ", ".join(sorted(self._sessions)) or "none"
            raise Agilent34411AConnectionError(
                f"unknown Agilent 34411A alias {selected!r}; known aliases: {known}"
            ) from exc

    def _connection_state(self, alias: str, driver: Agilent34411A) -> dict[str, Any]:
        """RFDS-002 Section 12.1 normalized connection-state dictionary."""

        if not driver.connected:
            return {
                "alias": alias,
                "resource": None,
                "connected": False,
                "communication_ok": False,
                "transport": None,
                "identity": None,
                "timeout_s": None,
                "state": "disconnected",
            }
        identity_str: str | None = None
        try:
            identity_str = driver.identify(refresh=False).raw
        except Exception:  # noqa: BLE001 - a stale/failed identity read must not prevent
            # reporting connection state; communication_ok below already reflects this as False.
            identity_str = None
        return {
            "alias": alias,
            "resource": driver.resource,
            "connected": True,
            "communication_ok": identity_str is not None,
            "transport": type(driver.transport).__name__,
            "identity": identity_str,
            "timeout_s": driver.timeout_s,
            "state": "connected",
        }

    # ------------------------------------------------------------------
    # RFDS-002 canonical connection keywords (task §7)
    # ------------------------------------------------------------------
    @keyword("Connect")
    def connect(
        self,
        resource: str | None = None,
        alias: str = "default",
        timeout_s: float | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Connect over VISA (GPIB/USB/LAN), or the bundled simulator with ``simulated=True``.

        Idempotent when ``alias`` is already connected to the same ``resource``.
        """

        selected_alias = str(alias).strip() or "default"
        if selected_alias in self._sessions:
            existing = self._sessions[selected_alias]
            if resource and existing.connected and str(existing.resource) != str(resource):
                raise Agilent34411AConnectionError(
                    f"alias {selected_alias!r} is already connected to {existing.resource!r}; "
                    f"disconnect it before connecting it to {resource!r}."
                )
            self._active_alias = selected_alias
            return self._connection_state(selected_alias, existing)

        simulated = _as_bool(options.pop("simulated", False), "simulated")
        if simulated:
            driver = Agilent34411A.connect_simulated()
            execution_mode = "SIMULATOR"
        else:
            if not resource:
                raise Agilent34411AValidationError("resource is required unless simulated=True")
            driver = Agilent34411A.connect_visa(str(resource), timeout_s=timeout_s or 5.0)
            execution_mode = "REAL_HARDWARE"
        run = self._ensure_evidence()
        if hasattr(run, "execution_mode"):
            # A run that mixes simulated and real aliases is honestly reported as
            # MIXED rather than silently keeping whichever mode connected first
            # (RFDS-008 §6.6 simulation honesty).
            if run.execution_mode == "NO_HARDWARE":
                run.execution_mode = execution_mode
            elif run.execution_mode != execution_mode:
                run.execution_mode = "MIXED"
        driver.transport = _evidence.InstrumentedTransport(driver.transport, run, selected_alias)
        self._sessions[selected_alias] = driver
        self._active_alias = selected_alias
        _rf_logger.info(f"Agilent34411A: connected alias={selected_alias!r} resource={driver.resource!r}")
        try:
            identity = driver.identify(refresh=True)
            run.record_device_identity(
                session_alias=selected_alias,
                manufacturer=getattr(identity, "manufacturer", None),
                model=getattr(identity, "model", None),
                serial_number=getattr(identity, "serial", None),
                firmware_version=getattr(identity, "firmware", None),
                raw_identity=getattr(identity, "raw", None),
                resource=driver.resource,
                execution_mode=execution_mode,
            )
        except Exception:  # noqa: BLE001, S110 - identity capture is best-effort evidence, not a connect precondition
            pass
        return self._connection_state(selected_alias, driver)

    @keyword("Disconnect")
    def disconnect(self, alias: str | None = None) -> None:
        """Idempotent: succeeds even if already disconnected."""

        selected = self._resolve_alias(alias)
        if selected is None or selected not in self._sessions:
            return
        self._sessions.pop(selected).close()
        if self._active_alias == selected:
            self._active_alias = next(iter(self._sessions), None)

    @keyword("Is Connected")
    def is_connected(self, alias: str | None = None) -> bool:
        selected = self._resolve_alias(alias)
        if selected is None or selected not in self._sessions:
            return False
        return self._sessions[selected].connected

    @keyword("Get Connection State")
    def get_connection_state(self, alias: str | None = None, refresh: bool = False) -> dict[str, Any]:
        selected = self._resolve_alias(alias)
        if selected is None or selected not in self._sessions:
            return {
                "alias": selected or "default",
                "resource": None,
                "connected": False,
                "communication_ok": False,
                "transport": None,
                "identity": None,
                "timeout_s": None,
                "state": "disconnected",
            }
        driver = self._sessions[selected]
        if _as_bool(refresh, "refresh") and driver.connected:
            try:
                driver.check_communication()
            except Exception:  # noqa: BLE001, S110 - a failed probe is itself the answer: it
                # shows up as communication_ok=False below, not as a raised error here.
                pass
        return self._connection_state(selected, driver)

    @keyword("Check Communication")
    def check_communication(self, alias: str | None = None) -> bool:
        return self._session(alias).check_communication()

    @keyword("Get Identity")
    def get_identity(self, alias: str | None = None, refresh: bool = True) -> str:
        return self._session(alias).identify(refresh=_as_bool(refresh, "refresh")).raw

    @keyword("Switch Multimeter")
    def switch_multimeter(self, alias: str) -> str:
        self._session(alias)
        self._active_alias = str(alias)
        return self._active_alias

    @keyword("Get Active Multimeter")
    def get_active_multimeter(self) -> str | None:
        return self._active_alias

    @keyword("List Multimeter Connections")
    def list_multimeter_connections(self) -> list[str]:
        return sorted(self._sessions)

    # ------------------------------------------------------------------
    # Function selection (task §8)
    # ------------------------------------------------------------------
    @keyword("Set Function")
    def set_function(self, function: str, alias: str | None = None) -> None:
        self._session(alias).set_function(function)

    @keyword("Get Function")
    def get_function(self, alias: str | None = None) -> str:
        return self._session(alias).get_function().value

    # ------------------------------------------------------------------
    # Per-function measurement configuration (task §8)
    # ------------------------------------------------------------------
    @keyword("Set Range")
    def set_range(self, function: str, range_value: float, alias: str | None = None) -> None:
        self._session(alias).set_range(function, float(range_value))

    @keyword("Get Range")
    def get_range(self, function: str, alias: str | None = None) -> float:
        return self._session(alias).get_range(function)

    @keyword("Set Auto Range")
    def set_auto_range(self, function: str, enabled: bool = True, alias: str | None = None) -> None:
        self._session(alias).set_auto_range(function, _as_bool(enabled, "enabled"))

    @keyword("Get Auto Range")
    def get_auto_range(self, function: str, alias: str | None = None) -> bool:
        return self._session(alias).get_auto_range(function)

    @keyword("Set Integration Time NPLC")
    def set_integration_time_nplc(self, function: str, nplc: float, alias: str | None = None) -> None:
        self._session(alias).set_integration_time_nplc(function, float(nplc))

    @keyword("Get Integration Time NPLC")
    def get_integration_time_nplc(self, function: str, alias: str | None = None) -> float:
        return self._session(alias).get_integration_time_nplc(function)

    @keyword("Set Integration Time Aperture")
    def set_integration_time_aperture(self, function: str, seconds: float, alias: str | None = None) -> None:
        self._session(alias).set_integration_time_aperture(function, float(seconds))

    @keyword("Get Integration Time Aperture")
    def get_integration_time_aperture(self, function: str, alias: str | None = None) -> float:
        return self._session(alias).get_integration_time_aperture(function)

    @keyword("Set Auto Zero")
    def set_auto_zero(self, function: str, mode: str, alias: str | None = None) -> None:
        """4-wire resistance is always auto-zero on and rejects this keyword (task §8)."""

        self._session(alias).set_auto_zero(function, mode)

    @keyword("Get Auto Zero")
    def get_auto_zero(self, function: str, alias: str | None = None) -> str:
        return self._session(alias).get_auto_zero(function).value

    @keyword("Set Offset Compensation")
    def set_offset_compensation(self, function: str, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_offset_compensation(function, _as_bool(enabled, "enabled"))

    @keyword("Get Offset Compensation")
    def get_offset_compensation(self, function: str, alias: str | None = None) -> bool:
        return self._session(alias).get_offset_compensation(function)

    @keyword("Set AC Filter Bandwidth")
    def set_ac_filter_bandwidth(self, function: str, filter_: str, alias: str | None = None) -> None:
        self._session(alias).set_ac_filter_bandwidth(function, filter_)

    @keyword("Get AC Filter Bandwidth")
    def get_ac_filter_bandwidth(self, function: str, alias: str | None = None) -> str:
        return self._session(alias).get_ac_filter_bandwidth(function).value

    @keyword("Set Input Impedance Auto")
    def set_input_impedance_auto(self, enabled: bool, alias: str | None = None) -> None:
        """DC voltage only — Hi-Z (>10 GOhm) vs fixed 10 MOhm on the three lowest ranges."""

        self._session(alias).set_input_impedance_auto(_as_bool(enabled, "enabled"))

    @keyword("Get Input Impedance Auto")
    def get_input_impedance_auto(self, alias: str | None = None) -> bool:
        return self._session(alias).get_input_impedance_auto()

    @keyword("Set Null")
    def set_null(self, function: str, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_null(function, _as_bool(enabled, "enabled"))

    @keyword("Get Null")
    def get_null(self, function: str, alias: str | None = None) -> bool:
        return self._session(alias).get_null(function)

    @keyword("Set Null Value")
    def set_null_value(self, function: str, value: float, alias: str | None = None) -> None:
        self._session(alias).set_null_value(function, float(value))

    @keyword("Get Null Value")
    def get_null_value(self, function: str, alias: str | None = None) -> float:
        return self._session(alias).get_null_value(function)

    @keyword("Get Measurement Settings")
    def get_measurement_settings(self, function: str | None = None, alias: str | None = None) -> dict[str, Any]:
        return _robot_value(self._session(alias).get_measurement_settings(function))

    # ------------------------------------------------------------------
    # Temperature (task §8)
    # ------------------------------------------------------------------
    @keyword("Set Temperature Probe Type")
    def set_temperature_probe_type(
        self, probe_type: str, thermistor_type: str | None = None, alias: str | None = None,
    ) -> None:
        self._session(alias).set_temperature_probe_type(probe_type, thermistor_type)

    @keyword("Get Temperature Probe Type")
    def get_temperature_probe_type(self, alias: str | None = None) -> str:
        return self._session(alias).get_temperature_probe_type().value

    @keyword("Set Temperature Units")
    def set_temperature_units(self, unit: str, alias: str | None = None) -> None:
        self._session(alias).set_temperature_units(unit)

    @keyword("Get Temperature Units")
    def get_temperature_units(self, alias: str | None = None) -> str:
        return self._session(alias).get_temperature_units().value

    # ------------------------------------------------------------------
    # Taking readings (task §8)
    # ------------------------------------------------------------------
    @keyword("Get Immediate Measurement")
    def get_immediate_measurement(self, alias: str | None = None):
        """Blocking, immediate trigger (READ?). Raises on the documented overload sentinel."""

        return self._session(alias).get_immediate_measurement()

    @keyword("Get Reading")
    def get_reading(self, alias: str | None = None):
        """Retrieves reading(s) already triggered (FETCh?), without erasing them."""

        return self._session(alias).get_reading()

    # ------------------------------------------------------------------
    # Math (task §9)
    # ------------------------------------------------------------------
    @keyword("Get Math Function")
    def get_math_function(self, alias: str | None = None) -> str:
        return self._session(alias).get_math_function().value

    @keyword("Is Math Enabled")
    def is_math_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).is_math_enabled()

    @keyword("Enable dB Measurement")
    def enable_db_measurement(self, alias: str | None = None) -> None:
        self._session(alias).enable_db_measurement()

    @keyword("Set dB Reference")
    def set_db_reference(self, value: float, alias: str | None = None) -> None:
        self._session(alias).set_db_reference(float(value))

    @keyword("Enable dBm Measurement")
    def enable_dbm_measurement(self, alias: str | None = None) -> None:
        self._session(alias).enable_dbm_measurement()

    @keyword("Set dBm Reference Resistance")
    def set_dbm_reference_resistance(self, ohms: float, alias: str | None = None) -> None:
        self._session(alias).set_dbm_reference_resistance(float(ohms))

    @keyword("Enable Statistics")
    def enable_statistics(self, alias: str | None = None) -> None:
        self._session(alias).enable_statistics()

    @keyword("Get Statistics")
    def get_statistics(self, alias: str | None = None) -> dict[str, Any]:
        return _robot_value(self._session(alias).get_statistics())

    @keyword("Clear Statistics")
    def clear_statistics(self, alias: str | None = None) -> None:
        self._session(alias).clear_statistics()

    @keyword("Enable Limit Test")
    def enable_limit_test(self, alias: str | None = None) -> None:
        self._session(alias).enable_limit_test()

    @keyword("Set Limits")
    def set_limits(self, low: float, high: float, alias: str | None = None) -> None:
        self._session(alias).set_limits(float(low), float(high))

    @keyword("Get Limits")
    def get_limits(self, alias: str | None = None) -> list[float]:
        return list(self._session(alias).get_limits())

    @keyword("Disable Math")
    def disable_math(self, alias: str | None = None) -> None:
        self._session(alias).disable_math()

    # ------------------------------------------------------------------
    # Trigger / sample (task §9)
    # ------------------------------------------------------------------
    @keyword("Set Trigger Source")
    def set_trigger_source(self, source: str, alias: str | None = None) -> None:
        """Raises if INTernal is requested on a function that doesn't support level triggering."""

        self._session(alias).set_trigger_source(source)

    @keyword("Get Trigger Source")
    def get_trigger_source(self, alias: str | None = None) -> str:
        return self._session(alias).get_trigger_source().value

    @keyword("Set Trigger Level")
    def set_trigger_level(self, level: float, alias: str | None = None) -> None:
        self._session(alias).set_trigger_level(float(level))

    @keyword("Get Trigger Level")
    def get_trigger_level(self, alias: str | None = None) -> float:
        return self._session(alias).get_trigger_level()

    @keyword("Set Trigger Slope")
    def set_trigger_slope(self, slope: str, alias: str | None = None) -> None:
        self._session(alias).set_trigger_slope(slope)

    @keyword("Get Trigger Slope")
    def get_trigger_slope(self, alias: str | None = None) -> str:
        return self._session(alias).get_trigger_slope().value

    @keyword("Set Trigger Count")
    def set_trigger_count(self, count: float, alias: str | None = None) -> None:
        self._session(alias).set_trigger_count(count)

    @keyword("Get Trigger Count")
    def get_trigger_count(self, alias: str | None = None) -> float:
        return self._session(alias).get_trigger_count()

    @keyword("Set Trigger Delay")
    def set_trigger_delay(self, seconds: float, alias: str | None = None) -> None:
        self._session(alias).set_trigger_delay(float(seconds))

    @keyword("Set Trigger Delay Auto")
    def set_trigger_delay_auto(self, alias: str | None = None) -> None:
        self._session(alias).set_trigger_delay_auto()

    @keyword("Get Trigger Settings")
    def get_trigger_settings(self, alias: str | None = None) -> dict[str, Any]:
        return _robot_value(self._session(alias).get_trigger_settings())

    @keyword("Set Sample Count")
    def set_sample_count(self, count: float, alias: str | None = None) -> None:
        self._session(alias).set_sample_count(count)

    @keyword("Get Sample Count")
    def get_sample_count(self, alias: str | None = None) -> float:
        return self._session(alias).get_sample_count()

    @keyword("Set Sample Source")
    def set_sample_source(self, source: str, alias: str | None = None) -> None:
        self._session(alias).set_sample_source(source)

    @keyword("Set Sample Timer Interval")
    def set_sample_timer_interval(self, seconds: float, alias: str | None = None) -> None:
        self._session(alias).set_sample_timer_interval(float(seconds))

    @keyword("Set Pre-Trigger Sample Count")
    def set_pretrigger_sample_count(self, count: float, alias: str | None = None) -> None:
        """Rejects a pre-trigger count >= the sample count before any device write."""

        self._session(alias).set_pretrigger_sample_count(count)

    @keyword("Trigger Now")
    def trigger_now(self, alias: str | None = None) -> None:
        """Only valid when Trigger Source is BUS."""

        self._session(alias).trigger_now()

    # ------------------------------------------------------------------
    # Reading memory and data logging (task §10)
    # ------------------------------------------------------------------
    @keyword("Get Latest Reading")
    def get_latest_reading(self, alias: str | None = None):
        return self._session(alias).get_latest_reading()

    @keyword("Get Most Recent Reading")
    def get_most_recent_reading(self, alias: str | None = None) -> float:
        return self._session(alias).get_most_recent_reading()

    @keyword("Get Reading Count")
    def get_reading_count(self, alias: str | None = None) -> int:
        return self._session(alias).get_reading_count()

    @keyword("Drain Readings")
    def drain_readings(self, count: int, alias: str | None = None) -> list[float]:
        """Removes and returns the oldest N readings (FIFO, destructive)."""

        return self._session(alias).drain_readings(int(count))

    @keyword("Copy Readings To Non-Volatile Memory")
    def copy_readings_to_nonvolatile_memory(self, alias: str | None = None) -> None:
        """The confirmed remote-driven data logging mechanism (task §10)."""

        self._session(alias).copy_readings_to_nonvolatile_memory()

    @keyword("Get Non-Volatile Reading Count")
    def get_nonvolatile_reading_count(self, alias: str | None = None) -> int:
        return self._session(alias).get_nonvolatile_reading_count()

    @keyword("Get Non-Volatile Readings")
    def get_nonvolatile_readings(self, alias: str | None = None) -> list[float]:
        return self._session(alias).get_nonvolatile_readings()

    @keyword("Clear Non-Volatile Readings")
    def clear_nonvolatile_readings(self, alias: str | None = None) -> None:
        self._session(alias).clear_nonvolatile_readings()

    @keyword("Drain Non-Volatile Readings")
    def drain_nonvolatile_readings(self, max_count: int | None = None, alias: str | None = None) -> list[float]:
        """Removes and returns up to max_count readings (destructive)."""

        return self._session(alias).drain_nonvolatile_readings(
            int(max_count) if max_count is not None else None
        )

    # ------------------------------------------------------------------
    # Instrument memory state storage (task §11)
    # ------------------------------------------------------------------
    @keyword("Save Setup To Instrument Memory")
    def save_setup_to_instrument_memory(self, slot: int, alias: str | None = None) -> None:
        self._session(alias).save_setup_to_instrument_memory(int(slot))

    @keyword("Restore Setup From Instrument Memory")
    def restore_setup_from_instrument_memory(self, slot: int, alias: str | None = None) -> None:
        """Rejects an empty/never-saved slot rather than silently reconfiguring (task §11)."""

        self._session(alias).restore_setup_from_instrument_memory(int(slot))

    @keyword("Get Instrument Memory Catalog")
    def get_instrument_memory_catalog(self, alias: str | None = None) -> list[int]:
        return self._session(alias).get_instrument_memory_catalog()

    @keyword("Rename Instrument Memory Slot")
    def rename_instrument_memory_slot(self, slot: int, name: str, alias: str | None = None) -> None:
        self._session(alias).rename_instrument_memory_slot(int(slot), name)

    @keyword("Get Instrument Memory Slot Name")
    def get_instrument_memory_slot_name(self, slot: int, alias: str | None = None) -> str:
        return self._session(alias).get_instrument_memory_slot_name(int(slot))

    @keyword("Delete Instrument Memory Slot")
    def delete_instrument_memory_slot(self, slot: int, alias: str | None = None) -> None:
        self._session(alias).delete_instrument_memory_slot(int(slot))

    @keyword("Delete All Instrument Memory Slots")
    def delete_all_instrument_memory_slots(self, alias: str | None = None) -> None:
        self._session(alias).delete_all_instrument_memory_slots()

    @keyword("Is Instrument Memory Slot Valid")
    def is_instrument_memory_slot_valid(self, slot: int, alias: str | None = None) -> bool:
        return self._session(alias).is_instrument_memory_slot_valid(int(slot))

    @keyword("Get Instrument Memory Slot Count")
    def get_instrument_memory_slot_count(self, alias: str | None = None) -> int:
        return self._session(alias).get_instrument_memory_slot_count()

    @keyword("Set Power-On State Recall")
    def set_power_on_state_recall(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_power_on_state_recall(_as_bool(enabled, "enabled"))

    @keyword("Set Power-On State")
    def set_power_on_state(self, slot: int, alias: str | None = None) -> None:
        self._session(alias).set_power_on_state(int(slot))

    # ------------------------------------------------------------------
    # Front panel / system (task §6, §2)
    # ------------------------------------------------------------------
    @keyword("Get Active Input Terminals")
    def get_active_input_terminals(self, alias: str | None = None) -> str:
        """Read-only. Never change the front/rear switch while signals are present."""

        return self._session(alias).get_active_input_terminals()

    @keyword("Set Beeper Enabled")
    def set_beeper_enabled(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_beeper_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get Beeper Enabled")
    def get_beeper_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_beeper_enabled()

    @keyword("Set Display Enabled")
    def set_display_enabled(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_display_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get Display Enabled")
    def get_display_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_display_enabled()

    @keyword("Set Display Text")
    def set_display_text(self, text: str, alias: str | None = None) -> None:
        self._session(alias).set_display_text(text)

    @keyword("Clear Display Text")
    def clear_display_text(self, alias: str | None = None) -> None:
        self._session(alias).clear_display_text()

    # ------------------------------------------------------------------
    # Calibration (Gate 3 — CALibration subsystem, behind a dedicated guard)
    # ------------------------------------------------------------------
    @keyword("Enable Calibration Mode")
    def enable_calibration_mode(self, confirmation: str, alias: str | None = None) -> None:
        self._session(alias).enable_calibration_mode(confirmation)

    @keyword("Unlock Calibration")
    def unlock_calibration(self, security_code: str, alias: str | None = None) -> None:
        self._session(alias).unlock_calibration(security_code)

    @keyword("Lock Calibration")
    def lock_calibration(self, alias: str | None = None) -> None:
        self._session(alias).lock_calibration()

    @keyword("Is Calibration Locked")
    def is_calibration_locked(self, alias: str | None = None) -> bool:
        """Read-only — harmless without the calibration guard enabled."""

        return self._session(alias).is_calibration_locked()

    @keyword("Set Calibration Security Code")
    def set_calibration_security_code(self, new_code: str, alias: str | None = None) -> None:
        self._session(alias).set_calibration_security_code(new_code)

    @keyword("Run Full Calibration")
    def run_full_calibration(self, alias: str | None = None) -> bool:
        return self._session(alias).run_full_calibration()

    @keyword("Run ADC Calibration")
    def run_adc_calibration(self, alias: str | None = None) -> float:
        return self._session(alias).run_adc_calibration()

    @keyword("Set Calibration Line Frequency")
    def set_calibration_line_frequency(self, hz: int, alias: str | None = None) -> None:
        self._session(alias).set_calibration_line_frequency(int(hz))

    @keyword("Get Calibration Line Frequency")
    def get_calibration_line_frequency(self, alias: str | None = None) -> int:
        return self._session(alias).get_calibration_line_frequency()

    @keyword("Get Actual Calibration Line Frequency")
    def get_actual_calibration_line_frequency(self, alias: str | None = None) -> float:
        """Read-only measurement readback — harmless without the calibration guard."""

        return self._session(alias).get_actual_calibration_line_frequency()

    @keyword("Store Calibration")
    def store_calibration(self, alias: str | None = None) -> None:
        self._session(alias).store_calibration()

    @keyword("Get Calibration Count")
    def get_calibration_count(self, alias: str | None = None) -> int:
        """Read-only — harmless without the calibration guard enabled."""

        return self._session(alias).get_calibration_count()

    @keyword("Set Calibration String")
    def set_calibration_string(self, text: str, alias: str | None = None) -> None:
        self._session(alias).set_calibration_string(text)

    @keyword("Get Calibration String")
    def get_calibration_string(self, alias: str | None = None) -> str:
        return self._session(alias).get_calibration_string()

    @keyword("Set Calibration Value")
    def set_calibration_value(self, value: float, alias: str | None = None) -> None:
        self._session(alias).set_calibration_value(float(value))

    @keyword("Get Calibration Value")
    def get_calibration_value(self, alias: str | None = None) -> float:
        return self._session(alias).get_calibration_value()

    # ------------------------------------------------------------------
    # LAN configuration (Gate 3 — SYSTem:COMMunicate:LAN subsystem)
    # ------------------------------------------------------------------
    @keyword("Set LAN DHCP Enabled")
    def set_lan_dhcp_enabled(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_lan_dhcp_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get LAN DHCP Enabled")
    def get_lan_dhcp_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_dhcp_enabled()

    @keyword("Set LAN IP Address")
    def set_lan_ip_address(self, address: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_ip_address(address)

    @keyword("Get LAN IP Address")
    def get_lan_ip_address(self, selector: str | None = None, alias: str | None = None) -> str:
        return self._session(alias).get_lan_ip_address(selector)

    @keyword("Set LAN Subnet Mask")
    def set_lan_subnet_mask(self, mask: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_subnet_mask(mask)

    @keyword("Get LAN Subnet Mask")
    def get_lan_subnet_mask(self, selector: str | None = None, alias: str | None = None) -> str:
        return self._session(alias).get_lan_subnet_mask(selector)

    @keyword("Set LAN Gateway")
    def set_lan_gateway(self, gateway: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_gateway(gateway)

    @keyword("Get LAN Gateway")
    def get_lan_gateway(self, selector: str | None = None, alias: str | None = None) -> str:
        return self._session(alias).get_lan_gateway(selector)

    @keyword("Set LAN DNS")
    def set_lan_dns(self, address: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_dns(address)

    @keyword("Get LAN DNS")
    def get_lan_dns(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_dns()

    @keyword("Set LAN Hostname")
    def set_lan_hostname(self, name: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_hostname(name)

    @keyword("Get LAN Hostname")
    def get_lan_hostname(self, selector: str | None = None, alias: str | None = None) -> str:
        return self._session(alias).get_lan_hostname(selector)

    @keyword("Set LAN Domain")
    def set_lan_domain(self, name: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_domain(name)

    @keyword("Get LAN Domain")
    def get_lan_domain(self, selector: str | None = None, alias: str | None = None) -> str:
        return self._session(alias).get_lan_domain(selector)

    @keyword("Set LAN Auto IP")
    def set_lan_auto_ip(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_lan_auto_ip(_as_bool(enabled, "enabled"))

    @keyword("Get LAN Auto IP")
    def get_lan_auto_ip(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_auto_ip()

    @keyword("Set LAN DDNS Enabled")
    def set_lan_ddns_enabled(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_lan_ddns_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get LAN DDNS Enabled")
    def get_lan_ddns_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_ddns_enabled()

    @keyword("Set LAN Keepalive")
    def set_lan_keepalive(self, seconds: float, alias: str | None = None) -> None:
        self._session(alias).set_lan_keepalive(float(seconds))

    @keyword("Get LAN Keepalive")
    def get_lan_keepalive(self, alias: str | None = None) -> float:
        return self._session(alias).get_lan_keepalive()

    @keyword("Get LAN Logical IP Address")
    def get_lan_logical_ip_address(self, alias: str | None = None) -> str:
        """Read-only."""

        return self._session(alias).get_lan_logical_ip_address()

    @keyword("Get LAN MAC Address")
    def get_lan_mac_address(self, alias: str | None = None) -> str:
        """Read-only."""

        return self._session(alias).get_lan_mac_address()

    @keyword("Get LAN Connection Status")
    def get_lan_connection_status(self, alias: str | None = None) -> str:
        """Read-only."""

        return self._session(alias).get_lan_connection_status()

    @keyword("Get LAN Control Connection Status")
    def get_lan_control_connection_status(self, alias: str | None = None) -> str:
        """Read-only."""

        return self._session(alias).get_lan_control_connection_status()

    @keyword("Set LAN Media Sense Enabled")
    def set_lan_mdns_enabled(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_lan_mdns_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get LAN Media Sense Enabled")
    def get_lan_mdns_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_mdns_enabled()

    @keyword("Set LAN NetBIOS Enabled")
    def set_lan_netbios_enabled(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_lan_netbios_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get LAN NetBIOS Enabled")
    def get_lan_netbios_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_netbios_enabled()

    @keyword("Set LAN Telnet Prompt")
    def set_lan_telnet_prompt(self, text: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_telnet_prompt(text)

    @keyword("Get LAN Telnet Prompt")
    def get_lan_telnet_prompt(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_telnet_prompt()

    @keyword("Set LAN Telnet Welcome Message")
    def set_lan_telnet_welcome_message(self, text: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_telnet_welcome_message(text)

    @keyword("Get LAN Telnet Welcome Message")
    def get_lan_telnet_welcome_message(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_telnet_welcome_message()

    @keyword("Clear LAN History")
    def clear_lan_history(self, alias: str | None = None) -> None:
        self._session(alias).clear_lan_history()

    @keyword("Get LAN History")
    def get_lan_history(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_history()

    # ------------------------------------------------------------------
    # Raw SCPI escape hatch (task §12)
    # ------------------------------------------------------------------
    @keyword("Enable Raw SCPI")
    def enable_raw_scpi(self, confirmation: str, alias: str | None = None) -> None:
        self._session(alias).enable_raw_scpi(confirmation)

    @keyword("Raw SCPI Query")
    def raw_scpi_query(self, command: str, alias: str | None = None) -> str:
        """Bypasses typed validation."""

        return self._session(alias).raw_query(command)

    @keyword("Raw SCPI Write")
    def raw_scpi_write(self, command: str, alias: str | None = None) -> None:
        """Bypasses typed validation."""

        self._session(alias).raw_write(command)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    @keyword("Export Diagnostic Bundle")
    def export_diagnostic_bundle(self, destination: str | None = None) -> str | None:
        """Zip this suite's RFDS-008 evidence run to ``destination`` for troubleshooting.

        Works with any number of connected aliases, and does not finalize the
        run — Robot's own suite-end hook (``_end_suite``) remains the point at
        which ``run_summary.json``/``evidence_manifest.json`` are written for
        the last time. Returns the archive path, or ``None`` if
        ``evidence_enabled=${FALSE}`` was passed to this library instance.
        """
        run = self._ensure_evidence()
        return run.export_diagnostic_bundle(None if destination in (None, "") else str(destination))
