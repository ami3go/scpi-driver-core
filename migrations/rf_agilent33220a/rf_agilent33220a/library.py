"""Robot Framework adapter for :mod:`agilent33220a`.

Keeps SCPI construction and validation entirely in the core driver
(task §5.2) — this module only converts arguments/results and manages
named sessions.

Every public keyword is automatically wrapped with an RFDS-008 evidence
operation record (see ``_instrument_all_public_keywords`` below, applied to
every ``@keyword``-decorated method with no per-method edits needed), and
every SCPI command/response is traced through ``evidence.TracingTransport``,
installed transparently around each connection's real transport in
``connect()``. See ``rf_agilent33220a/evidence.py`` and
``docs/logging_and_evidence.md``. Pass ``evidence_enabled=${FALSE}`` to
``Agilent33220ALibrary()`` to disable it.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
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


from agilent33220a import Agilent33220A
from agilent33220a.exceptions import Agilent33220AConnectionError, Agilent33220AValidationError


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
    raise Agilent33220AValidationError(f"{name} must be a Boolean, got {value!r}")


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


def _evidenced(func):
    """Wrap one already-``@keyword``-decorated method with an evidence operation record.

    Applied to every public keyword automatically by
    ``_instrument_all_public_keywords`` rather than one-by-one — with 116
    keywords on this driver, per-method decorator edits would be impractical
    to keep correct. Reads ``func.robot_name``/``robot_tags`` (already set by
    ``@keyword`` by the time this runs, since it's applied as a whole-class
    post-processing step after the class body finishes executing) and copies
    them onto the wrapper so Robot's introspection and any contract tests
    keep seeing the same public keyword surface.
    """
    capability = getattr(func, "robot_name", None) or func.__name__.replace("_", " ").title()
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(self: Agilent33220ALibrary, *args: Any, **kwargs: Any) -> Any:
        run = self._ensure_evidence()
        bound = signature.bind_partial(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {key: value for key, value in bound.arguments.items() if key != "self"}
        session_alias = self._resolve_alias(arguments.get("alias"))
        with run.record_operation(capability, arguments=arguments, session_alias=session_alias) as op:
            result = func(self, *args, **kwargs)
            op.set_result(result)
            return result

    wrapper.robot_name = capability
    wrapper.robot_tags = getattr(func, "robot_tags", ())
    return wrapper


def _instrument_all_public_keywords(cls):
    """Class decorator: wraps every ``@keyword``-decorated method with :func:`_evidenced`.

    Must be applied *below* ``@library(...)`` in the decorator stack (closer
    to the class body) so it runs first, wrapping the plain keyword methods
    before ``@library`` inspects the finished class.
    """
    for name, member in list(vars(cls).items()):
        if callable(member) and getattr(member, "robot_name", None):
            setattr(cls, name, _evidenced(member))
    return cls


@library(scope="SUITE", version="26.2", auto_keywords=False)
@_instrument_all_public_keywords
class Agilent33220ALibrary:
    """Robot Framework keywords for the Agilent (Keysight) 33220A waveform generator.

    The RFDS-002 canonical connection keywords (``Connect``, ``Disconnect``,
    ``Is Connected``, ``Get Connection State``, ``Check Communication``,
    ``Get Identity``) are the primary, documented connection API — see the
    task document, task §7. No hardware is touched on library import.

    Every keyword call is recorded as RFDS-008 evidence (arguments, duration,
    the underlying SCPI traffic, failures) under
    ``results/session/rf_agilent33220a/`` for the lifetime of this library
    instance (one evidence run per suite, since ``ROBOT_LIBRARY_SCOPE`` is
    ``SUITE``) — see ``evidence.py`` and ``docs/logging_and_evidence.md``.
    """

    ROBOT_LIBRARY_SCOPE = "SUITE"
    ROBOT_LIBRARY_VERSION = "26.2"

    def __init__(self, evidence_enabled: Any = True) -> None:
        self._sessions: dict[str, Agilent33220A] = {}
        self._active_alias: str | None = None
        self._evidence_enabled = _as_bool(evidence_enabled, "evidence_enabled")
        self._evidence: Any = None
        self.ROBOT_LIBRARY_LISTENER = self

    def _ensure_evidence(self) -> Any:
        """Lazily create (or return) this suite's :class:`evidence.EvidenceRun`.

        Created on first keyword call, not in ``__init__``, so constructing
        the library never touches disk by itself.
        """
        if self._evidence is None:
            if self._evidence_enabled:
                self._evidence = _evidence.EvidenceRun(driver_id="rf_agilent33220a", activity="session")
            else:
                self._evidence = _evidence.NullEvidenceRun()
        return self._evidence

    # ------------------------------------------------------------------
    # Robot listener (v2 API, library-scoped via ROBOT_LIBRARY_LISTENER) —
    # feeds suite/test/keyword identity into evidence.py's contextvars for
    # correlation, and finalizes the evidence run at suite end.
    # ------------------------------------------------------------------
    def _start_suite(self, name: str, attributes: dict[str, Any]) -> None:
        # `name` (not `attributes`) is used: attributes is not reliably a plain v2
        # dict for a library-internal (ROBOT_LIBRARY_LISTENER) listener in every
        # execution mode — dry-run in particular has been observed passing the raw
        # running-model object instead, which has no `.get()` (found by actually
        # running --dryrun against tests/robot/acceptance.robot while building this).
        del attributes
        _evidence.set_current_suite(name)

    def _start_test(self, name: str, attributes: dict[str, Any]) -> None:
        del attributes
        _evidence.set_current_test(name)

    def _end_test(self, name: str, attributes: dict[str, Any]) -> None:
        del name, attributes
        _evidence.set_current_test(None)

    def _start_keyword(self, name: str, attributes: dict[str, Any]) -> None:
        del attributes
        _evidence.set_current_keyword(name)

    def _end_keyword(self, name: str, attributes: dict[str, Any]) -> None:
        del name, attributes
        _evidence.set_current_keyword(None)

    def _end_suite(self, name: str, attributes: dict[str, Any]) -> None:
        del name, attributes
        errors: list[str] = []
        for alias in list(self._sessions):
            try:
                self._sessions[alias].close()
            except Exception as exc:  # noqa: BLE001 - cleanup must not hide an earlier suite failure
                errors.append(f"{alias!r}: {exc}")
                _rf_logger.warn(f"Agilent33220A: cleanup for {alias!r} reported: {exc}")  # noqa: G010 - robot.api.logger has no .warning
        self._sessions.clear()
        self._active_alias = None
        _evidence.set_current_suite(None)
        if self._evidence is not None:
            self._evidence.finalize(status="PASS" if not errors else "FAIL")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _resolve_alias(self, alias: str | None) -> str | None:
        return str(alias) if alias not in (None, "") else self._active_alias

    def _session(self, alias: str | None = None) -> Agilent33220A:
        selected = self._resolve_alias(alias)
        if selected is None:
            raise Agilent33220AConnectionError(
                "no Agilent 33220A connection is active; call 'Connect' first"
            )
        try:
            return self._sessions[selected]
        except KeyError as exc:
            known = ", ".join(sorted(self._sessions)) or "none"
            raise Agilent33220AConnectionError(
                f"unknown Agilent 33220A alias {selected!r}; known aliases: {known}"
            ) from exc

    def _connection_state(self, alias: str, driver: Agilent33220A) -> dict[str, Any]:
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
            # Unwrapped: report the real transport class (Pyvisa/Simulated), not the
            # TracingTransport evidence wrapper installed around it in connect().
            "transport": type(_evidence.unwrap_transport(driver.transport)).__name__,
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
                raise Agilent33220AConnectionError(
                    f"alias {selected_alias!r} is already connected to {existing.resource!r}; "
                    f"disconnect it before connecting it to {resource!r}."
                )
            self._active_alias = selected_alias
            return self._connection_state(selected_alias, existing)

        simulated = _as_bool(options.pop("simulated", False), "simulated")
        if simulated:
            driver = Agilent33220A.connect_simulated()
        else:
            if not resource:
                raise Agilent33220AValidationError("resource is required unless simulated=True")
            driver = Agilent33220A.connect_visa(str(resource), timeout_s=timeout_s or 5.0)
        # Trace every SCPI write/query this session makes from here on, transparently to
        # the core driver (see evidence.TracingTransport) — installed only after the real
        # transport is confirmed open, so a failed connect_visa/connect_simulated call
        # above still surfaces its own untraced exception normally.
        run = self._ensure_evidence()
        run.note_connection_mode(simulated)
        driver.transport = _evidence.TracingTransport(driver.transport, run, session_alias=selected_alias)
        self._sessions[selected_alias] = driver
        self._active_alias = selected_alias
        _rf_logger.info(f"Agilent33220A: connected alias={selected_alias!r} resource={driver.resource!r}")
        state = self._connection_state(selected_alias, driver)
        run.record_device_identity(
            selected_alias,
            resource=driver.resource,
            transport_type=type(_evidence.unwrap_transport(driver.transport)).__name__,
            identity=state.get("identity"),
            simulated=simulated,
        )
        return state

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

    @keyword("Switch Generator")
    def switch_generator(self, alias: str) -> str:
        self._session(alias)
        self._active_alias = str(alias)
        return self._active_alias

    @keyword("Get Active Generator")
    def get_active_generator(self) -> str | None:
        return self._active_alias

    @keyword("List Generator Connections")
    def list_generator_connections(self) -> list[str]:
        return sorted(self._sessions)

    # ------------------------------------------------------------------
    # Output configuration (task §8)
    # ------------------------------------------------------------------
    @keyword("Set Function")
    def set_function(self, function: str, alias: str | None = None) -> None:
        """Guarded per task §6 item 5: raises a typed error naming the actual
        adjusted value if the instrument reports a settings conflict."""

        self._session(alias).set_function(function)

    @keyword("Get Function")
    def get_function(self, alias: str | None = None) -> str:
        return self._session(alias).get_function().value

    @keyword("Set Frequency")
    def set_frequency(self, frequency: float, alias: str | None = None) -> None:
        self._session(alias).set_frequency(float(frequency))

    @keyword("Get Frequency")
    def get_frequency(self, alias: str | None = None) -> float:
        return self._session(alias).get_frequency()

    @keyword("Set Amplitude")
    def set_amplitude(self, amplitude: float, alias: str | None = None) -> None:
        """Validated per task §6 item 4 (Vpp < 2*(Vmax-|Voffset|)) before any device I/O."""

        self._session(alias).set_amplitude(float(amplitude))

    @keyword("Get Amplitude")
    def get_amplitude(self, alias: str | None = None) -> float:
        return self._session(alias).get_amplitude()

    @keyword("Set Amplitude Unit")
    def set_amplitude_unit(self, unit: str, alias: str | None = None) -> None:
        self._session(alias).set_amplitude_unit(unit)

    @keyword("Get Amplitude Unit")
    def get_amplitude_unit(self, alias: str | None = None) -> str:
        return self._session(alias).get_amplitude_unit().value

    @keyword("Set Offset")
    def set_offset(self, offset: float, alias: str | None = None) -> None:
        """Validated per task §6 item 4 (Vpp < 2*(Vmax-|Voffset|)) before any device I/O."""

        self._session(alias).set_offset(float(offset))

    @keyword("Get Offset")
    def get_offset(self, alias: str | None = None) -> float:
        return self._session(alias).get_offset()

    @keyword("Set Output Load")
    def set_output_load(self, ohms: str, alias: str | None = None) -> None:
        self._session(alias).set_output_load(ohms)

    @keyword("Get Output Load")
    def get_output_load(self, alias: str | None = None) -> str:
        return self._session(alias).get_output_load()

    @keyword("Set Output Polarity")
    def set_output_polarity(self, polarity: str, alias: str | None = None) -> None:
        self._session(alias).set_output_polarity(polarity)

    @keyword("Get Output Polarity")
    def get_output_polarity(self, alias: str | None = None) -> str:
        return self._session(alias).get_output_polarity().value

    @keyword("Set Square Duty Cycle")
    def set_square_duty_cycle(self, percent: float, alias: str | None = None) -> None:
        self._session(alias).set_square_duty_cycle(float(percent))

    @keyword("Get Square Duty Cycle")
    def get_square_duty_cycle(self, alias: str | None = None) -> float:
        return self._session(alias).get_square_duty_cycle()

    @keyword("Set Ramp Symmetry")
    def set_ramp_symmetry(self, percent: float, alias: str | None = None) -> None:
        self._session(alias).set_ramp_symmetry(float(percent))

    @keyword("Get Ramp Symmetry")
    def get_ramp_symmetry(self, alias: str | None = None) -> float:
        return self._session(alias).get_ramp_symmetry()

    @keyword("Configure Output")
    def configure_output(
        self,
        function: str,
        frequency: float,
        amplitude: float,
        offset: float = 0.0,
        enable_output: bool = False,
        alias: str | None = None,
    ) -> None:
        """APPLy-backed convenience keyword. Never leaves the output enabled as an
        undocumented side effect (task §6 item 1) — pass ``enable_output=True``
        explicitly if that's what the test actually wants."""

        self._session(alias).configure_output(
            function, float(frequency), float(amplitude), float(offset),
            enable_output=_as_bool(enable_output, "enable_output"),
        )

    @keyword("Enable Output")
    def enable_output(self, alias: str | None = None) -> None:
        self._session(alias).enable_output()

    @keyword("Disable Output")
    def disable_output(self, alias: str | None = None) -> None:
        self._session(alias).disable_output()

    @keyword("Is Output Enabled")
    def is_output_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).is_output_enabled()

    @keyword("Get Output Settings")
    def get_output_settings(self, alias: str | None = None) -> dict[str, Any]:
        return _robot_value(self._session(alias).get_output_settings())

    @keyword("Lock Front Panel")
    def lock_front_panel(self, alias: str | None = None) -> None:
        self._session(alias).lock_front_panel()

    @keyword("Unlock Front Panel")
    def unlock_front_panel(self, alias: str | None = None) -> None:
        self._session(alias).unlock_front_panel()

    @keyword("Is Front Panel Locked")
    def is_front_panel_locked(self, alias: str | None = None) -> bool:
        return self._session(alias).is_front_panel_locked()

    @keyword("Set Display Text")
    def set_display_text(self, text: str, alias: str | None = None) -> None:
        self._session(alias).set_display_text(text)

    @keyword("Clear Display Text")
    def clear_display_text(self, alias: str | None = None) -> None:
        self._session(alias).clear_display_text()

    @keyword("Enable Display")
    def enable_display(self, alias: str | None = None) -> None:
        self._session(alias).enable_display()

    @keyword("Disable Display")
    def disable_display(self, alias: str | None = None) -> None:
        self._session(alias).disable_display()

    # ------------------------------------------------------------------
    # Pulse (task §9)
    # ------------------------------------------------------------------
    @keyword("Configure Pulse")
    def configure_pulse(
        self,
        period: float | None = None,
        width: float | None = None,
        duty_cycle: float | None = None,
        transition: float | None = None,
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_pulse(
            period=None if period is None else float(period),
            width=None if width is None else float(width),
            duty_cycle=None if duty_cycle is None else float(duty_cycle),
            transition=None if transition is None else float(transition),
        )

    # ------------------------------------------------------------------
    # Modulation (task §9)
    # ------------------------------------------------------------------
    @keyword("Configure Amplitude Modulation")
    def configure_amplitude_modulation(
        self, shape: str, frequency: float, depth_percent: float, source: str = "INTernal",
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_amplitude_modulation(shape, float(frequency), float(depth_percent), source)

    @keyword("Enable Amplitude Modulation")
    def enable_amplitude_modulation(self, alias: str | None = None) -> None:
        self._session(alias).enable_amplitude_modulation()

    @keyword("Disable Amplitude Modulation")
    def disable_amplitude_modulation(self, alias: str | None = None) -> None:
        self._session(alias).disable_amplitude_modulation()

    @keyword("Configure Frequency Modulation")
    def configure_frequency_modulation(
        self, shape: str, frequency: float, deviation_hz: float, source: str = "INTernal",
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_frequency_modulation(shape, float(frequency), float(deviation_hz), source)

    @keyword("Enable Frequency Modulation")
    def enable_frequency_modulation(self, alias: str | None = None) -> None:
        self._session(alias).enable_frequency_modulation()

    @keyword("Disable Frequency Modulation")
    def disable_frequency_modulation(self, alias: str | None = None) -> None:
        self._session(alias).disable_frequency_modulation()

    @keyword("Configure Phase Modulation")
    def configure_phase_modulation(
        self, shape: str, frequency: float, deviation_degrees: float, source: str = "INTernal",
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_phase_modulation(shape, float(frequency), float(deviation_degrees), source)

    @keyword("Enable Phase Modulation")
    def enable_phase_modulation(self, alias: str | None = None) -> None:
        self._session(alias).enable_phase_modulation()

    @keyword("Disable Phase Modulation")
    def disable_phase_modulation(self, alias: str | None = None) -> None:
        self._session(alias).disable_phase_modulation()

    @keyword("Configure Frequency Shift Keying")
    def configure_frequency_shift_keying(
        self, hop_frequency: float, rate_hz: float, source: str = "INTernal",
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_frequency_shift_keying(float(hop_frequency), float(rate_hz), source)

    @keyword("Enable Frequency Shift Keying")
    def enable_frequency_shift_keying(self, alias: str | None = None) -> None:
        self._session(alias).enable_frequency_shift_keying()

    @keyword("Disable Frequency Shift Keying")
    def disable_frequency_shift_keying(self, alias: str | None = None) -> None:
        self._session(alias).disable_frequency_shift_keying()

    @keyword("Configure Pulse Width Modulation")
    def configure_pulse_width_modulation(
        self, shape: str, frequency: float, deviation_seconds: float, source: str = "INTernal",
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_pulse_width_modulation(shape, float(frequency), float(deviation_seconds), source)

    @keyword("Enable Pulse Width Modulation")
    def enable_pulse_width_modulation(self, alias: str | None = None) -> None:
        self._session(alias).enable_pulse_width_modulation()

    @keyword("Disable Pulse Width Modulation")
    def disable_pulse_width_modulation(self, alias: str | None = None) -> None:
        self._session(alias).disable_pulse_width_modulation()

    # ------------------------------------------------------------------
    # Sweep (task §9)
    # ------------------------------------------------------------------
    @keyword("Configure Frequency Sweep")
    def configure_frequency_sweep(
        self, start: float, stop: float, spacing: str = "LINear", time_s: float = 1.0,
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_frequency_sweep(float(start), float(stop), spacing, float(time_s))

    @keyword("Enable Sweep")
    def enable_sweep(self, alias: str | None = None) -> None:
        self._session(alias).enable_sweep()

    @keyword("Disable Sweep")
    def disable_sweep(self, alias: str | None = None) -> None:
        self._session(alias).disable_sweep()

    @keyword("Set Sweep Marker Frequency")
    def set_sweep_marker_frequency(self, frequency: float, alias: str | None = None) -> None:
        self._session(alias).set_sweep_marker_frequency(float(frequency))

    @keyword("Get Sweep Marker Frequency")
    def get_sweep_marker_frequency(self, alias: str | None = None) -> float:
        return self._session(alias).get_sweep_marker_frequency()

    @keyword("Enable Sweep Marker")
    def enable_sweep_marker(self, alias: str | None = None) -> None:
        self._session(alias).enable_sweep_marker()

    @keyword("Disable Sweep Marker")
    def disable_sweep_marker(self, alias: str | None = None) -> None:
        self._session(alias).disable_sweep_marker()

    # ------------------------------------------------------------------
    # Burst (task §9)
    # ------------------------------------------------------------------
    @keyword("Configure Burst")
    def configure_burst(
        self, mode: str, cycles: float, period: float | None = None, phase_degrees: float = 0.0,
        alias: str | None = None,
    ) -> None:
        self._session(alias).configure_burst(
            mode, float(cycles), None if period is None else float(period), float(phase_degrees)
        )

    @keyword("Enable Burst")
    def enable_burst(self, alias: str | None = None) -> None:
        self._session(alias).enable_burst()

    @keyword("Disable Burst")
    def disable_burst(self, alias: str | None = None) -> None:
        self._session(alias).disable_burst()

    @keyword("Set Burst Gate Polarity")
    def set_burst_gate_polarity(self, polarity: str, alias: str | None = None) -> None:
        self._session(alias).set_burst_gate_polarity(polarity)

    # ------------------------------------------------------------------
    # Trigger (task §9)
    # ------------------------------------------------------------------
    @keyword("Set Trigger Source")
    def set_trigger_source(self, source: str, alias: str | None = None) -> None:
        self._session(alias).set_trigger_source(source)

    @keyword("Get Trigger Source")
    def get_trigger_source(self, alias: str | None = None) -> str:
        return self._session(alias).get_trigger_source().value

    @keyword("Set Trigger Slope")
    def set_trigger_slope(self, slope: str, alias: str | None = None) -> None:
        self._session(alias).set_trigger_slope(slope)

    @keyword("Get Trigger Slope")
    def get_trigger_slope(self, alias: str | None = None) -> str:
        return self._session(alias).get_trigger_slope().value

    @keyword("Get Trigger Settings")
    def get_trigger_settings(self, alias: str | None = None) -> dict[str, Any]:
        return _robot_value(self._session(alias).get_trigger_settings())

    @keyword("Trigger Now")
    def trigger_now(self, alias: str | None = None) -> None:
        """Only valid when Trigger Source is BUS."""

        self._session(alias).trigger_now()

    # ------------------------------------------------------------------
    # Arbitrary waveform (task §10)
    # ------------------------------------------------------------------
    @keyword("Load Arbitrary Waveform")
    def load_arbitrary_waveform(self, values: list, alias: str | None = None) -> None:
        """Always fills the VOLATILE slot; use 'Copy Arbitrary Waveform To Nonvolatile'
        to persist it under a chosen name (task §6 item 6)."""

        self._session(alias).load_arbitrary_waveform([float(v) for v in values])

    @keyword("Copy Arbitrary Waveform To Nonvolatile")
    def copy_arbitrary_waveform_to_nonvolatile(self, name: str, alias: str | None = None) -> None:
        self._session(alias).copy_arbitrary_waveform_to_nonvolatile(name)

    @keyword("Select Arbitrary Waveform")
    def select_arbitrary_waveform(self, name: str, alias: str | None = None) -> None:
        self._session(alias).select_arbitrary_waveform(name)

    @keyword("List Arbitrary Waveforms")
    def list_arbitrary_waveforms(self, alias: str | None = None) -> list[str]:
        return self._session(alias).list_arbitrary_waveforms()

    @keyword("Delete Arbitrary Waveform")
    def delete_arbitrary_waveform(self, name: str, alias: str | None = None) -> None:
        self._session(alias).delete_arbitrary_waveform(name)

    @keyword("Delete All Arbitrary Waveforms")
    def delete_all_arbitrary_waveforms(self, alias: str | None = None) -> None:
        self._session(alias).delete_all_arbitrary_waveforms()

    @keyword("Get Arbitrary Waveform Attributes")
    def get_arbitrary_waveform_attributes(self, name: str, alias: str | None = None) -> dict[str, Any]:
        return _robot_value(self._session(alias).get_arbitrary_waveform_attributes(name))

    # ------------------------------------------------------------------
    # Setup save/restore (task §11)
    # ------------------------------------------------------------------
    @keyword("Save Setup")
    def save_setup(self, path: str, alias: str | None = None) -> None:
        """Primary implementation: *LRN? written verbatim to a host file."""

        self._session(alias).save_setup(Path(path))

    @keyword("Restore Setup")
    def restore_setup(self, path: str, alias: str | None = None) -> None:
        """Resends a *LRN?-captured setup string; verified via the error queue."""

        self._session(alias).restore_setup(Path(path))

    @keyword("Save Setup To Instrument Memory")
    def save_setup_to_instrument_memory(self, slot: int, alias: str | None = None) -> None:
        self._session(alias).save_setup_to_instrument_memory(int(slot))

    @keyword("Restore Setup From Instrument Memory")
    def restore_setup_from_instrument_memory(self, slot: int, alias: str | None = None) -> None:
        """Rejects an empty/never-saved slot rather than silently reconfiguring (task §11)."""

        self._session(alias).restore_setup_from_instrument_memory(int(slot))

    @keyword("Restore Factory Setup")
    def restore_factory_setup(self, alias: str | None = None) -> None:
        self._session(alias).restore_factory_setup()

    # ------------------------------------------------------------------
    # Calibration (Gate 3)
    # ------------------------------------------------------------------
    @keyword("Enable Calibration Mode")
    def enable_calibration_mode(self, confirmation: str, alias: str | None = None) -> None:
        """Two-tier safety guard: requires the exact text "ENABLE CALIBRATION",
        distinct from 'Enable Raw SCPI'. Must be called before any other
        calibration-affecting keyword below (except the read-only queries)."""

        self._session(alias).enable_calibration_mode(confirmation)

    @keyword("Run Calibration")
    def run_calibration(self, alias: str | None = None) -> bool:
        """CAL? — performs a full self-calibration. Returns True on pass, False on fail."""

        return self._session(alias).run_calibration()

    @keyword("Unlock Calibration")
    def unlock_calibration(self, security_code: str, alias: str | None = None) -> None:
        self._session(alias).unlock_calibration(security_code)

    @keyword("Lock Calibration")
    def lock_calibration(self, alias: str | None = None) -> None:
        self._session(alias).lock_calibration()

    @keyword("Is Calibration Locked")
    def is_calibration_locked(self, alias: str | None = None) -> bool:
        """Read-only query; does not require 'Enable Calibration Mode' first."""

        return self._session(alias).is_calibration_locked()

    @keyword("Set Calibration Security Code")
    def set_calibration_security_code(self, new_code: str, alias: str | None = None) -> None:
        self._session(alias).set_calibration_security_code(new_code)

    @keyword("Set Calibration Step")
    def set_calibration_step(self, step: int, alias: str | None = None) -> None:
        self._session(alias).set_calibration_step(int(step))

    @keyword("Get Calibration Step")
    def get_calibration_step(self, alias: str | None = None) -> int:
        return self._session(alias).get_calibration_step()

    @keyword("Set Calibration Value")
    def set_calibration_value(self, value: float, alias: str | None = None) -> None:
        self._session(alias).set_calibration_value(float(value))

    @keyword("Get Calibration Value")
    def get_calibration_value(self, alias: str | None = None) -> float:
        return self._session(alias).get_calibration_value()

    @keyword("Get Calibration Count")
    def get_calibration_count(self, alias: str | None = None) -> int:
        """Read-only query; does not require 'Enable Calibration Mode' first."""

        return self._session(alias).get_calibration_count()

    @keyword("Set Calibration String")
    def set_calibration_string(self, text: str, alias: str | None = None) -> None:
        self._session(alias).set_calibration_string(text)

    @keyword("Get Calibration String")
    def get_calibration_string(self, alias: str | None = None) -> str:
        return self._session(alias).get_calibration_string()

    # ------------------------------------------------------------------
    # GPIB/LAN interface configuration (Gate 3)
    # ------------------------------------------------------------------
    @keyword("Set GPIB Address")
    def set_gpib_address(self, address: int, alias: str | None = None) -> None:
        self._session(alias).set_gpib_address(int(address))

    @keyword("Get GPIB Address")
    def get_gpib_address(self, alias: str | None = None) -> int:
        return self._session(alias).get_gpib_address()

    @keyword("Set LAN Auto IP")
    def set_lan_auto_ip(self, enabled: bool, alias: str | None = None) -> None:
        self._session(alias).set_lan_auto_ip(_as_bool(enabled, "enabled"))

    @keyword("Get LAN Auto IP")
    def get_lan_auto_ip(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_auto_ip()

    @keyword("Set LAN IP Address")
    def set_lan_ip_address(self, address: str, alias: str | None = None) -> None:
        self._session(alias).set_lan_ip_address(address)

    @keyword("Get LAN IP Address")
    def get_lan_ip_address(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_ip_address()

    @keyword("Get LAN Logical IP Address")
    def get_lan_logical_ip_address(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_logical_ip_address()

    @keyword("Get LAN MAC Address")
    def get_lan_mac_address(self, alias: str | None = None) -> str:
        return self._session(alias).get_lan_mac_address()

    @keyword("Set LAN Media Sense Enabled")
    def set_lan_media_sense_enabled(self, enabled: bool, alias: str | None = None) -> None:
        """SYSTem:COMMunicate:LAN:MEDiasense — LAN link-loss detection/auto-restart,
        not mDNS despite the mnemonic (see docstring on the core driver method)."""

        self._session(alias).set_lan_media_sense_enabled(_as_bool(enabled, "enabled"))

    @keyword("Get LAN Media Sense Enabled")
    def get_lan_media_sense_enabled(self, alias: str | None = None) -> bool:
        return self._session(alias).get_lan_media_sense_enabled()

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

        Works at any point in the suite and does not finalize the run —
        suite end (``_end_suite``) remains where ``run_summary.json``/
        ``evidence_manifest.json`` are written for the last time. Returns the
        archive path, or ``None`` if ``evidence_enabled=${FALSE}`` was passed
        when this library was imported.
        """
        run = self._ensure_evidence()
        return run.export_diagnostic_bundle(None if destination in (None, "") else str(destination))
