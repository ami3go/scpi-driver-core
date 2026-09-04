"""Deterministic in-process Agilent 33220A simulator.

Implements the command subset the core driver actually issues (task doc
§13), as a text-in/bytes-out dispatcher so the driver's real SCPI strings
are exercised exactly as they would be against hardware.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

_IDN = "Agilent Technologies,33220A,SIM00001,2.03-1.19-2.00-58-00"

# Documented default amplitude (100 mVpp into 50 ohms) and the max amplitude
# this simulator enforces for the Vpp < 2 * (Vmax - |Voffset|) check (task §6
# item 4). A real 33220A's actual Vmax varies by function/load; this
# simulator uses one fixed, documented value so the constraint is testable
# deterministically without needing to model every function's real limit.
_DEFAULT_AMPLITUDE_VPP = 0.1
_MAX_AMPLITUDE_VPP = 10.0


@dataclass
class _OutputState:
    function: str = "SIN"
    frequency: float = 1000.0
    amplitude: float = _DEFAULT_AMPLITUDE_VPP
    amplitude_unit: str = "VPP"
    offset: float = 0.0
    output_enabled: bool = False
    output_load: str = "50"
    polarity: str = "NORM"
    output_sync: bool = True
    square_duty_cycle: float = 50.0
    ramp_symmetry: float = 100.0


@dataclass
class _PulseState:
    period: float = 1e-3
    hold: str = "WIDT"
    width: float = 1e-4
    duty_cycle: float = 50.0
    transition: float = 1e-8


@dataclass
class _ModState:
    function: str = "SIN"
    frequency: float = 100.0
    depth: float = 100.0  # AM
    deviation: float = 100.0  # FM/PM/PWM
    deviation_dcycle: float = 10.0  # PWM
    source: str = "INT"
    state: bool = False


@dataclass
class _SweepState:
    start: float = 100.0
    stop: float = 1000.0
    spacing: str = "LIN"
    time: float = 1.0
    state: bool = False
    marker_frequency: float = 500.0
    marker_enabled: bool = False


@dataclass
class _BurstState:
    mode: str = "TRIG"
    ncycles: float = 1.0
    period: float = 1e-3
    phase: float = 0.0
    state: bool = False
    gate_polarity: str = "NORM"


@dataclass
class _TriggerState:
    source: str = "IMM"
    slope: str = "POS"
    output_trigger: bool = False
    output_trigger_slope: str = "POS"


@dataclass
class _FrontPanelState:
    locked: bool = False
    lock_exclude: str = "NONE"
    display_on: bool = True
    display_text: str = ""
    beeper: bool = True


@dataclass
class _CalibrationState:
    """Default locked (secured), matching a real 33220A as shipped from the factory."""

    locked: bool = True
    security_code: str = "AT33220A"
    step: int = 0
    value: float = 0.0
    count: int = 0
    string: str = ""


@dataclass
class _InterfaceState:
    gpib_address: int = 10
    lan_auto_ip: bool = True
    lan_ip_address: str = "169.254.2.20"
    lan_logical_ip_address: str = "169.254.2.20"
    lan_mac_address: str = "00-30-D3-00-10-41"
    lan_media_sense: bool = True
    lan_netbios: bool = True
    lan_telnet_prompt: str = "33220A>"
    lan_telnet_welcome_message: str = "Welcome to Agilent's 33220A Waveform Generator"


class SimAgilent33220AInstrument:
    """A small, deterministic stand-in for a real 33220A over VISA."""

    def __init__(self) -> None:
        self.output = _OutputState()
        self.pulse = _PulseState()
        self.am = _ModState(frequency=100.0, depth=100.0)
        self.fm = _ModState(frequency=100.0, deviation=100.0)
        self.pm = _ModState(frequency=100.0, deviation=180.0)
        self.pwm = _ModState(frequency=100.0, deviation=1e-5)
        self.fsk = {"frequency": 100.0, "rate": 10.0, "source": "INT", "state": False}
        self.sweep = _SweepState()
        self.burst = _BurstState()
        self.trigger = _TriggerState()
        self.panel = _FrontPanelState()
        self.calibration = _CalibrationState()
        self.interface = _InterfaceState()
        self.arb_waveforms: dict[str, list[float]] = {}
        self.nonvolatile_waveforms: dict[str, list[float]] = {}
        self.selected_arb: str | None = None
        self.memory_slots: dict[int, str] = {}
        self.memory_valid: set[int] = set()
        self.settings_conflict_next_function_change = False
        self.apply_calls = 0
        self.trigger_now_calls = 0
        # Test hook (matches the rf_agilent34411a/rf_ea_ps9000t force_overload
        # convention): forces CAL? to report FAIL so that path is testable
        # offline without a real miscalibrated instrument.
        self.force_calibration_failure = False
        self._events: list[tuple[int, str]] = []

    # -- public dispatch -------------------------------------------------

    def dispatch(self, command: str) -> bytes:
        command = command.strip()
        if not command:
            return b""

        # "TRIGger" and "*TRG" execute an immediate trigger; bare TRIGger (no
        # colon, no query) is a distinct pseudo-argument-free command from
        # "TRIGger:SOURce"/"TRIGger:SLOPe".
        if command.upper() in ("TRIGGER", "*TRG"):
            return self._trigger_now("", False)

        if ";" in command:
            return self._dispatch_concatenated(command)

        head, _, rest = command.partition(" ")
        rest = rest.strip()
        is_query = head.endswith("?")
        handler_name = head[:-1] if is_query else head

        try:
            handler = self._ROUTES[handler_name.upper()]
        except KeyError:
            self._push_event(113, f"Undefined header;{command}")
            return b""
        return handler(self, rest, is_query)

    def _dispatch_concatenated(self, command: str) -> bytes:
        """Replay a ';'-separated command sequence, e.g. a resent *LRN? string.

        Same convention as `rf_tbs1000c`'s simulator: a segment whose head
        contains ':' is fully qualified and sets the current command group;
        a bare "KEYWORD arg" segment inherits that group. A leading ':' also
        always marks a fresh top-level command, *even when the head that
        follows has no further colon of its own* (e.g. ":OUTPut OFF" after a
        "VOLTage:..." group) — without that, a bare single-word head like
        "OUTPut" would wrongly inherit whatever group preceded it instead of
        resetting to its own name as the new group.
        """

        group = ""
        last_response = b""
        for segment in command.split(";"):
            segment = segment.strip()
            if not segment:
                continue
            explicit_root = segment.startswith(":")
            if explicit_root:
                segment = segment[1:].strip()
            head, _, rest = segment.partition(" ")
            if explicit_root or ":" in head:
                group = head.rsplit(":", 1)[0] if ":" in head else head
                full_command = segment
            elif group:
                full_command = f"{group}:{head}" + (f" {rest}" if rest else "")
            else:
                full_command = segment
            last_response = self.dispatch(full_command)
        return last_response

    def _push_event(self, code: int, message: str) -> None:
        self._events.append((code, message))

    # -- standard/common commands ----------------------------------------

    def _idn(self, _rest: str, _is_query: bool) -> bytes:
        return _IDN.encode("ascii")

    def _cls(self, _rest: str, _is_query: bool) -> bytes:
        self._events.clear()
        return b""

    def _rst(self, _rest: str, _is_query: bool) -> bytes:
        self.__init__()  # type: ignore[misc]
        return b""

    def _tst(self, _rest: str, _is_query: bool) -> bytes:
        return b"0"

    def _opc(self, _rest: str, _is_query: bool) -> bytes:
        return b"1"

    def _wai(self, _rest: str, _is_query: bool) -> bytes:
        return b""

    def _psc(self, rest: str, is_query: bool) -> bytes:
        return b"1" if is_query else b""

    def _stb(self, _rest: str, _is_query: bool) -> bytes:
        return b"0" if not self._events else b"4"

    def _sre(self, rest: str, is_query: bool) -> bytes:
        return b"0" if is_query else b""

    def _esr(self, _rest: str, _is_query: bool) -> bytes:
        return b"0" if not self._events else b"32"

    def _ese(self, rest: str, is_query: bool) -> bytes:
        return b"0" if is_query else b""

    def _system_error(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b'+0,"No error"'
        code, message = self._events.pop(0)
        return f'{code},"{message}"'.encode("ascii")

    def _system_version(self, _rest: str, _is_query: bool) -> bytes:
        return b"1999.0"

    def _status_preset(self, _rest: str, _is_query: bool) -> bytes:
        return b""

    def _lrn(self, _rest: str, _is_query: bool) -> bytes:
        return self._learn_string().encode("ascii")

    def _learn_string(self) -> str:
        out = self.output
        return (
            f"FUNCtion {out.function};FREQuency {out.frequency:.6E};"
            f"VOLTage {out.amplitude:.6E};VOLTage:OFFSet {out.offset:.6E};"
            f"VOLTage:UNIT {out.amplitude_unit};"
            f":OUTPut {'ON' if out.output_enabled else 'OFF'};"
            f":OUTPut:LOAD {out.output_load};POLarity {out.polarity};"
        )

    # -- front panel -------------------------------------------------------

    def _system_klock(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return (b"1" if self.panel.locked else b"0")
        self.panel.locked = rest.strip().upper() in ("ON", "1")
        return b""

    def _system_klock_exclude(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.panel.lock_exclude.encode("ascii")
        self.panel.lock_exclude = rest.strip().upper()
        return b""

    def _display(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.panel.display_on else b"0"
        self.panel.display_on = rest.strip().upper() in ("ON", "1")
        return b""

    def _display_text(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.panel.display_text}"'.encode("ascii")
        self.panel.display_text = rest.strip().strip('"')
        return b""

    def _display_text_clear(self, _rest: str, _is_query: bool) -> bytes:
        self.panel.display_text = ""
        return b""

    def _system_beeper(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.panel.beeper else b"0"
        self.panel.beeper = rest.strip().upper() in ("ON", "1")
        return b""

    # -- APPLy -------------------------------------------------------------

    def _apply(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            out = self.output
            return f'"{out.function} {out.frequency:.6E},{out.amplitude:.6E},{out.offset:.6E}"'.encode("ascii")
        return b""

    def _make_apply_handler(function_code: str):
        def handler(self: SimAgilent33220AInstrument, rest: str, _is_query: bool) -> bytes:
            self.apply_calls += 1
            parts = [p.strip() for p in rest.split(",") if p.strip()]
            self.output.function = function_code
            if len(parts) >= 1 and parts[0].upper() not in ("DEF", "DEFAULT"):
                self.output.frequency = float(parts[0])
            if len(parts) >= 2 and parts[1].upper() not in ("DEF", "DEFAULT"):
                self.output.amplitude = float(parts[1])
            if len(parts) >= 3:
                self.output.offset = float(parts[2])
            # Documented behavior: APPLy always enables the output.
            self.output.output_enabled = True
            return b""

        return handler

    _apply_sin = _make_apply_handler("SIN")
    _apply_squ = _make_apply_handler("SQU")
    _apply_ramp = _make_apply_handler("RAMP")
    _apply_puls = _make_apply_handler("PULS")
    _apply_nois = _make_apply_handler("NOIS")
    _apply_dc = _make_apply_handler("DC")
    _apply_user = _make_apply_handler("USER")

    # -- output configuration ----------------------------------------------

    def _function(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.output.function.encode("ascii")
        requested = rest.strip().upper()
        if self.settings_conflict_next_function_change:
            self.settings_conflict_next_function_change = False
            self.output.frequency = min(self.output.frequency, 2.0e5)
            self._push_event(
                -221, f"Settings conflict;frequency adjusted to {self.output.frequency:.6E}"
            )
        self.output.function = requested
        return b""

    def _frequency(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.output.frequency:.6E}".encode("ascii")
        self.output.frequency = self._resolve_value(rest, minimum=1e-6, maximum=2.0e7)
        return b""

    def _voltage(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            if rest.strip().upper() == "MAXIMUM":
                return f"{_MAX_AMPLITUDE_VPP:.6E}".encode("ascii")
            return f"{self.output.amplitude:.6E}".encode("ascii")
        self.output.amplitude = self._resolve_value(rest, minimum=0.0, maximum=_MAX_AMPLITUDE_VPP)
        return b""

    def _voltage_offset(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            if rest.strip().upper() == "MAXIMUM":
                return f"{_MAX_AMPLITUDE_VPP:.6E}".encode("ascii")
            return f"{self.output.offset:.6E}".encode("ascii")
        self.output.offset = self._resolve_value(rest, minimum=-10.0, maximum=10.0)
        return b""

    def _voltage_unit(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.output.amplitude_unit.encode("ascii")
        self.output.amplitude_unit = rest.strip().upper()
        return b""

    def _function_square_dcycle(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.output.square_duty_cycle:.4E}".encode("ascii")
        self.output.square_duty_cycle = float(rest)
        return b""

    def _function_ramp_symmetry(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.output.ramp_symmetry:.4E}".encode("ascii")
        self.output.ramp_symmetry = float(rest)
        return b""

    def _output(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.output.output_enabled else b"0"
        self.output.output_enabled = rest.strip().upper() in ("ON", "1")
        return b""

    def _output_load(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.output.output_load.encode("ascii")
        self.output.output_load = rest.strip().upper()
        return b""

    def _output_polarity(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.output.polarity.encode("ascii")
        self.output.polarity = rest.strip().upper()
        return b""

    def _output_sync(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.output.output_sync else b"0"
        self.output.output_sync = rest.strip().upper() in ("ON", "1")
        return b""

    def _output_trigger(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.trigger.output_trigger else b"0"
        self.trigger.output_trigger = rest.strip().upper() in ("ON", "1")
        return b""

    def _output_trigger_slope(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.output_trigger_slope.encode("ascii")
        self.trigger.output_trigger_slope = rest.strip().upper()
        return b""

    @staticmethod
    def _resolve_value(rest: str, *, minimum: float, maximum: float) -> float:
        token = rest.strip().upper()
        if token == "MINIMUM":
            return minimum
        if token == "MAXIMUM":
            return maximum
        return float(rest)

    # -- pulse ---------------------------------------------------------------

    def _pulse_period(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pulse.period:.6E}".encode("ascii")
        self.pulse.period = float(rest)
        return b""

    def _function_pulse_hold(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.pulse.hold.encode("ascii")
        self.pulse.hold = rest.strip().upper()
        return b""

    def _function_pulse_width(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pulse.width:.6E}".encode("ascii")
        self.pulse.width = float(rest)
        return b""

    def _function_pulse_dcycle(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pulse.duty_cycle:.4E}".encode("ascii")
        self.pulse.duty_cycle = float(rest)
        return b""

    def _function_pulse_transition(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pulse.transition:.6E}".encode("ascii")
        self.pulse.transition = float(rest)
        return b""

    # -- modulation ----------------------------------------------------------

    def _make_mod_handlers(prefix: str, attr: str):
        def internal_function(self: SimAgilent33220AInstrument, rest: str, is_query: bool) -> bytes:
            state = getattr(self, attr)
            if is_query:
                return state.function.encode("ascii")
            state.function = rest.strip().upper()
            return b""

        def internal_frequency(self: SimAgilent33220AInstrument, rest: str, is_query: bool) -> bytes:
            state = getattr(self, attr)
            if is_query:
                return f"{state.frequency:.6E}".encode("ascii")
            state.frequency = float(rest)
            return b""

        def source(self: SimAgilent33220AInstrument, rest: str, is_query: bool) -> bytes:
            state = getattr(self, attr)
            if is_query:
                return state.source.encode("ascii")
            state.source = rest.strip().upper()
            return b""

        def enabled(self: SimAgilent33220AInstrument, rest: str, is_query: bool) -> bytes:
            state = getattr(self, attr)
            if is_query:
                return b"1" if state.state else b"0"
            state.state = rest.strip().upper() in ("ON", "1")
            return b""

        return internal_function, internal_frequency, source, enabled

    _am_internal_function, _am_internal_frequency, _am_source, _am_state = _make_mod_handlers("AM", "am")
    _fm_internal_function, _fm_internal_frequency, _fm_source, _fm_state = _make_mod_handlers("FM", "fm")
    _pm_internal_function, _pm_internal_frequency, _pm_source, _pm_state = _make_mod_handlers("PM", "pm")
    _pwm_internal_function, _pwm_internal_frequency, _pwm_source, _pwm_state = _make_mod_handlers("PWM", "pwm")

    def _am_depth(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.am.depth:.4E}".encode("ascii")
        self.am.depth = float(rest)
        return b""

    def _fm_deviation(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.fm.deviation:.6E}".encode("ascii")
        self.fm.deviation = float(rest)
        return b""

    def _pm_deviation(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pm.deviation:.4E}".encode("ascii")
        self.pm.deviation = float(rest)
        return b""

    def _pwm_deviation(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pwm.deviation:.6E}".encode("ascii")
        self.pwm.deviation = float(rest)
        return b""

    def _pwm_deviation_dcycle(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.pwm.deviation_dcycle:.4E}".encode("ascii")
        self.pwm.deviation_dcycle = float(rest)
        return b""

    def _fskey_frequency(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.fsk['frequency']:.6E}".encode("ascii")
        self.fsk["frequency"] = float(rest)
        return b""

    def _fskey_internal_rate(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.fsk['rate']:.6E}".encode("ascii")
        self.fsk["rate"] = float(rest)
        return b""

    def _fskey_source(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.fsk["source"]).encode("ascii")
        self.fsk["source"] = rest.strip().upper()
        return b""

    def _fskey_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.fsk["state"] else b"0"
        self.fsk["state"] = rest.strip().upper() in ("ON", "1")
        return b""

    def _unit_angle(self, rest: str, is_query: bool) -> bytes:
        return b"DEG" if is_query else b""

    # -- sweep -----------------------------------------------------------

    def _freq_start(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.sweep.start:.6E}".encode("ascii")
        self.sweep.start = float(rest)
        return b""

    def _freq_stop(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.sweep.stop:.6E}".encode("ascii")
        self.sweep.stop = float(rest)
        return b""

    def _sweep_spacing(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.sweep.spacing.encode("ascii")
        self.sweep.spacing = rest.strip().upper()
        return b""

    def _sweep_time(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.sweep.time:.6E}".encode("ascii")
        self.sweep.time = float(rest)
        return b""

    def _sweep_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.sweep.state else b"0"
        self.sweep.state = rest.strip().upper() in ("ON", "1")
        return b""

    def _marker_frequency(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.sweep.marker_frequency:.6E}".encode("ascii")
        self.sweep.marker_frequency = float(rest)
        return b""

    def _marker(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.sweep.marker_enabled else b"0"
        self.sweep.marker_enabled = rest.strip().upper() in ("ON", "1")
        return b""

    # -- burst -------------------------------------------------------------

    def _burst_mode(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.burst.mode.encode("ascii")
        self.burst.mode = rest.strip().upper()
        return b""

    def _burst_ncycles(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.burst.ncycles:.6E}".encode("ascii")
        token = rest.strip().upper()
        self.burst.ncycles = math.inf if token == "INFINITY" else float(rest)
        return b""

    def _burst_internal_period(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.burst.period:.6E}".encode("ascii")
        self.burst.period = float(rest)
        return b""

    def _burst_phase(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.burst.phase:.4E}".encode("ascii")
        self.burst.phase = float(rest)
        return b""

    def _burst_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.burst.state else b"0"
        self.burst.state = rest.strip().upper() in ("ON", "1")
        return b""

    def _burst_gate_polarity(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.burst.gate_polarity.encode("ascii")
        self.burst.gate_polarity = rest.strip().upper()
        return b""

    # -- trigger -------------------------------------------------------------

    def _trigger_source(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.source.encode("ascii")
        self.trigger.source = rest.strip().upper()
        return b""

    def _trigger_slope(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.slope.encode("ascii")
        self.trigger.slope = rest.strip().upper()
        return b""

    def _trigger_now(self, _rest: str, _is_query: bool) -> bytes:
        if self.trigger.source != "BUS":
            self._push_event(-211, "Trigger ignored;TRIGger:SOURce is not BUS")
        self.trigger_now_calls += 1
        return b""

    # -- arbitrary waveform ---------------------------------------------------

    def _data(self, rest: str, _is_query: bool) -> bytes:
        return self._load_arb(rest, dac=False)

    def _data_dac(self, rest: str, _is_query: bool) -> bytes:
        return self._load_arb(rest, dac=True)

    def _load_arb(self, rest: str, *, dac: bool) -> bytes:
        # "VOLATILE, v1, v2, ..." — the destination is always VOLATILE for a
        # fresh upload; DATA:COPY is the only way to persist it.
        _dest, _, values_text = rest.partition(",")
        values = [float(v) for v in values_text.split(",") if v.strip()]
        if not values:
            self._push_event(-222, "Data out of range;no waveform values supplied")
            return b""
        self.arb_waveforms["VOLATILE"] = values
        self.selected_arb = "VOLATILE"
        return b""

    def _data_copy(self, rest: str, _is_query: bool) -> bytes:
        parts = [p.strip() for p in rest.split(",")]
        name = parts[0]
        if "VOLATILE" not in self.arb_waveforms:
            self._push_event(-222, "Data out of range;no VOLATILE waveform to copy")
            return b""
        self.nonvolatile_waveforms[name] = list(self.arb_waveforms["VOLATILE"])
        return b""

    def _data_catalog(self, _rest: str, _is_query: bool) -> bytes:
        names = sorted(self.arb_waveforms)
        return ",".join(f'"{n}"' for n in names).encode("ascii")

    def _data_nvolatile_catalog(self, _rest: str, _is_query: bool) -> bytes:
        names = sorted(self.nonvolatile_waveforms)
        return ",".join(f'"{n}"' for n in names).encode("ascii")

    def _data_nvolatile_free(self, _rest: str, _is_query: bool) -> bytes:
        return b"10"

    def _data_delete(self, rest: str, _is_query: bool) -> bytes:
        name = rest.strip().strip('"')
        if name not in self.arb_waveforms and name not in self.nonvolatile_waveforms:
            self._push_event(-224, f"Illegal parameter value;unknown arb {name!r}")
            return b""
        self.arb_waveforms.pop(name, None)
        self.nonvolatile_waveforms.pop(name, None)
        return b""

    def _data_delete_all(self, _rest: str, _is_query: bool) -> bytes:
        self.arb_waveforms.clear()
        self.nonvolatile_waveforms.clear()
        return b""

    def _data_attribute_average(self, rest: str, _is_query: bool) -> bytes:
        values = self._arb_values(rest)
        return f"{(sum(values) / len(values)):.6E}".encode("ascii") if values else b"0.0E0"

    def _data_attribute_cfactor(self, rest: str, _is_query: bool) -> bytes:
        values = self._arb_values(rest)
        if not values:
            return b"0.0E0"
        rms = math.sqrt(sum(v * v for v in values) / len(values))
        peak = max(abs(v) for v in values)
        return f"{(peak / rms if rms else 0.0):.6E}".encode("ascii")

    def _data_attribute_points(self, rest: str, _is_query: bool) -> bytes:
        return str(len(self._arb_values(rest))).encode("ascii")

    def _data_attribute_ptpeak(self, rest: str, _is_query: bool) -> bytes:
        values = self._arb_values(rest)
        return f"{(max(values) - min(values) if values else 0.0):.6E}".encode("ascii")

    def _arb_values(self, rest: str) -> list[float]:
        name = rest.strip().strip('"') or self.selected_arb or "VOLATILE"
        return self.arb_waveforms.get(name) or self.nonvolatile_waveforms.get(name) or []

    def _function_user(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return (self.selected_arb or "VOLATILE").encode("ascii")
        name = rest.strip().strip('"')
        if name not in self.arb_waveforms and name not in self.nonvolatile_waveforms:
            self._push_event(-224, f"Illegal parameter value;unknown arb {name!r}")
            return b""
        self.selected_arb = name
        return b""

    def _format_border(self, rest: str, is_query: bool) -> bytes:
        return b"NORM" if is_query else b""

    # -- calibration -------------------------------------------------------

    def _cal(self, _rest: str, _is_query: bool) -> bytes:
        """CAL? — per the manual, requires the instrument to be unsecured first."""

        if self.calibration.locked:
            self._push_event(702, "Calibration error; calibration memory is secured")
            return b"1"
        self.calibration.count += 1
        return b"1" if self.force_calibration_failure else b"0"

    def _cal_secure_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.calibration.locked else b"0"
        parts = [p.strip() for p in rest.split(",", 1)]
        token = parts[0].upper() if parts else ""
        if token in ("ON", "1"):
            self.calibration.locked = True
            return b""
        if token in ("OFF", "0"):
            code = parts[1] if len(parts) > 1 else ""
            if code != self.calibration.security_code:
                self._push_event(703, "Calibration error; secure code provided was invalid")
                return b""
            self.calibration.locked = False
            return b""
        self._push_event(-224, f"Illegal parameter value;{rest!r}")
        return b""

    def _cal_secure_code(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b""
        if self.calibration.locked:
            self._push_event(702, "Calibration error; calibration memory is secured")
            return b""
        self.calibration.security_code = rest.strip()
        return b""

    def _cal_setup(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.calibration.step).encode("ascii")
        self.calibration.step = int(float(rest))
        return b""

    def _cal_value(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.calibration.value:.6E}".encode("ascii")
        self.calibration.value = float(rest)
        return b""

    def _cal_count(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.calibration.count).encode("ascii")

    def _cal_string(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.calibration.string}"'.encode("ascii")
        if self.calibration.locked:
            self._push_event(702, "Calibration error; calibration memory is secured")
            return b""
        text = rest.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        self.calibration.string = text[:40]
        return b""

    # -- GPIB/LAN interface configuration -----------------------------------

    def _system_comm_gpib_address(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.interface.gpib_address).encode("ascii")
        self.interface.gpib_address = int(float(rest))
        return b""

    def _system_comm_lan_autoip(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.interface.lan_auto_ip else b"0"
        self.interface.lan_auto_ip = rest.strip().upper() in ("ON", "1")
        return b""

    def _system_comm_lan_ipaddress(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.interface.lan_ip_address.encode("ascii")
        self.interface.lan_ip_address = rest.strip()
        return b""

    def _system_comm_lan_lipaddress(self, _rest: str, _is_query: bool) -> bytes:
        return self.interface.lan_logical_ip_address.encode("ascii")

    def _system_comm_lan_mac(self, _rest: str, _is_query: bool) -> bytes:
        return self.interface.lan_mac_address.encode("ascii")

    def _system_comm_lan_mediasense(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.interface.lan_media_sense else b"0"
        self.interface.lan_media_sense = rest.strip().upper() in ("ON", "1")
        return b""

    def _system_comm_lan_netbios(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.interface.lan_netbios else b"0"
        self.interface.lan_netbios = rest.strip().upper() in ("ON", "1")
        return b""

    def _system_comm_lan_telnet_prompt(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.interface.lan_telnet_prompt}"'.encode("ascii")
        self.interface.lan_telnet_prompt = rest.strip().strip('"')
        return b""

    def _system_comm_lan_telnet_wmessage(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.interface.lan_telnet_welcome_message}"'.encode("ascii")
        self.interface.lan_telnet_welcome_message = rest.strip().strip('"')
        return b""

    # -- state storage ---------------------------------------------------

    def _sav(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        self.memory_slots[slot] = self._learn_string()
        self.memory_valid.add(slot)
        return b""

    def _rcl(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        if slot not in self.memory_valid:
            self._push_event(-224, f"Illegal parameter value;memory state {slot} is empty")
            return b""
        self.dispatch(self.memory_slots[slot])
        return b""

    def _memory_state_valid(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        return b"1" if slot in self.memory_valid else b"0"

    def _memory_nstates(self, _rest: str, _is_query: bool) -> bytes:
        return b"5"

    # -- factories evaluated at class body scope --------------------------

    _ROUTES: ClassVar[dict[str, object]]


SimAgilent33220AInstrument._ROUTES = {
    "*IDN": SimAgilent33220AInstrument._idn,
    "*CLS": SimAgilent33220AInstrument._cls,
    "*RST": SimAgilent33220AInstrument._rst,
    "*TST": SimAgilent33220AInstrument._tst,
    "*OPC": SimAgilent33220AInstrument._opc,
    "*WAI": SimAgilent33220AInstrument._wai,
    "*PSC": SimAgilent33220AInstrument._psc,
    "*STB": SimAgilent33220AInstrument._stb,
    "*SRE": SimAgilent33220AInstrument._sre,
    "*ESR": SimAgilent33220AInstrument._esr,
    "*ESE": SimAgilent33220AInstrument._ese,
    "*LRN": SimAgilent33220AInstrument._lrn,
    "*SAV": SimAgilent33220AInstrument._sav,
    "*RCL": SimAgilent33220AInstrument._rcl,
    "SYSTEM:ERROR": SimAgilent33220AInstrument._system_error,
    "SYSTEM:VERSION": SimAgilent33220AInstrument._system_version,
    "STATUS:PRESET": SimAgilent33220AInstrument._status_preset,
    "SYSTEM:KLOCK": SimAgilent33220AInstrument._system_klock,
    "SYSTEM:KLOCK:EXCLUDE": SimAgilent33220AInstrument._system_klock_exclude,
    "DISPLAY": SimAgilent33220AInstrument._display,
    "DISPLAY:TEXT": SimAgilent33220AInstrument._display_text,
    "DISPLAY:TEXT:CLEAR": SimAgilent33220AInstrument._display_text_clear,
    "SYSTEM:BEEPER": SimAgilent33220AInstrument._system_beeper,
    "APPLY": SimAgilent33220AInstrument._apply,
    "APPLY:SINUSOID": SimAgilent33220AInstrument._apply_sin,
    "APPLY:SQUARE": SimAgilent33220AInstrument._apply_squ,
    "APPLY:RAMP": SimAgilent33220AInstrument._apply_ramp,
    "APPLY:PULSE": SimAgilent33220AInstrument._apply_puls,
    "APPLY:NOISE": SimAgilent33220AInstrument._apply_nois,
    "APPLY:DC": SimAgilent33220AInstrument._apply_dc,
    "APPLY:USER": SimAgilent33220AInstrument._apply_user,
    "FUNCTION": SimAgilent33220AInstrument._function,
    "FUNCTION:USER": SimAgilent33220AInstrument._function_user,
    "FREQUENCY": SimAgilent33220AInstrument._frequency,
    "VOLTAGE": SimAgilent33220AInstrument._voltage,
    "VOLTAGE:OFFSET": SimAgilent33220AInstrument._voltage_offset,
    "VOLTAGE:UNIT": SimAgilent33220AInstrument._voltage_unit,
    "FUNCTION:SQUARE:DCYCLE": SimAgilent33220AInstrument._function_square_dcycle,
    "FUNCTION:RAMP:SYMMETRY": SimAgilent33220AInstrument._function_ramp_symmetry,
    "OUTPUT": SimAgilent33220AInstrument._output,
    "OUTPUT:LOAD": SimAgilent33220AInstrument._output_load,
    "OUTPUT:POLARITY": SimAgilent33220AInstrument._output_polarity,
    "OUTPUT:SYNC": SimAgilent33220AInstrument._output_sync,
    "OUTPUT:TRIGGER": SimAgilent33220AInstrument._output_trigger,
    "OUTPUT:TRIGGER:SLOPE": SimAgilent33220AInstrument._output_trigger_slope,
    "PULSE:PERIOD": SimAgilent33220AInstrument._pulse_period,
    "FUNCTION:PULSE:HOLD": SimAgilent33220AInstrument._function_pulse_hold,
    "FUNCTION:PULSE:WIDTH": SimAgilent33220AInstrument._function_pulse_width,
    "FUNCTION:PULSE:DCYCLE": SimAgilent33220AInstrument._function_pulse_dcycle,
    "FUNCTION:PULSE:TRANSITION": SimAgilent33220AInstrument._function_pulse_transition,
    "AM:INTERNAL:FUNCTION": SimAgilent33220AInstrument._am_internal_function,
    "AM:INTERNAL:FREQUENCY": SimAgilent33220AInstrument._am_internal_frequency,
    "AM:DEPTH": SimAgilent33220AInstrument._am_depth,
    "AM:SOURCE": SimAgilent33220AInstrument._am_source,
    "AM:STATE": SimAgilent33220AInstrument._am_state,
    "FM:INTERNAL:FUNCTION": SimAgilent33220AInstrument._fm_internal_function,
    "FM:INTERNAL:FREQUENCY": SimAgilent33220AInstrument._fm_internal_frequency,
    "FM:DEVIATION": SimAgilent33220AInstrument._fm_deviation,
    "FM:SOURCE": SimAgilent33220AInstrument._fm_source,
    "FM:STATE": SimAgilent33220AInstrument._fm_state,
    "PM:INTERNAL:FUNCTION": SimAgilent33220AInstrument._pm_internal_function,
    "PM:INTERNAL:FREQUENCY": SimAgilent33220AInstrument._pm_internal_frequency,
    "PM:DEVIATION": SimAgilent33220AInstrument._pm_deviation,
    "PM:SOURCE": SimAgilent33220AInstrument._pm_source,
    "PM:STATE": SimAgilent33220AInstrument._pm_state,
    "PWM:INTERNAL:FUNCTION": SimAgilent33220AInstrument._pwm_internal_function,
    "PWM:INTERNAL:FREQUENCY": SimAgilent33220AInstrument._pwm_internal_frequency,
    "PWM:DEVIATION": SimAgilent33220AInstrument._pwm_deviation,
    "PWM:DEVIATION:DCYCLE": SimAgilent33220AInstrument._pwm_deviation_dcycle,
    "PWM:SOURCE": SimAgilent33220AInstrument._pwm_source,
    "PWM:STATE": SimAgilent33220AInstrument._pwm_state,
    "FSKEY:FREQUENCY": SimAgilent33220AInstrument._fskey_frequency,
    "FSKEY:INTERNAL:RATE": SimAgilent33220AInstrument._fskey_internal_rate,
    "FSKEY:SOURCE": SimAgilent33220AInstrument._fskey_source,
    "FSKEY:STATE": SimAgilent33220AInstrument._fskey_state,
    "UNIT:ANGLE": SimAgilent33220AInstrument._unit_angle,
    "FREQUENCY:START": SimAgilent33220AInstrument._freq_start,
    "FREQUENCY:STOP": SimAgilent33220AInstrument._freq_stop,
    "SWEEP:SPACING": SimAgilent33220AInstrument._sweep_spacing,
    "SWEEP:TIME": SimAgilent33220AInstrument._sweep_time,
    "SWEEP:STATE": SimAgilent33220AInstrument._sweep_state,
    "MARKER:FREQUENCY": SimAgilent33220AInstrument._marker_frequency,
    "MARKER": SimAgilent33220AInstrument._marker,
    "BURST:MODE": SimAgilent33220AInstrument._burst_mode,
    "BURST:NCYCLES": SimAgilent33220AInstrument._burst_ncycles,
    "BURST:INTERNAL:PERIOD": SimAgilent33220AInstrument._burst_internal_period,
    "BURST:PHASE": SimAgilent33220AInstrument._burst_phase,
    "BURST:STATE": SimAgilent33220AInstrument._burst_state,
    "BURST:GATE:POLARITY": SimAgilent33220AInstrument._burst_gate_polarity,
    "TRIGGER:SOURCE": SimAgilent33220AInstrument._trigger_source,
    "TRIGGER:SLOPE": SimAgilent33220AInstrument._trigger_slope,
    "DATA": SimAgilent33220AInstrument._data,
    "DATA:DAC": SimAgilent33220AInstrument._data_dac,
    "DATA:COPY": SimAgilent33220AInstrument._data_copy,
    "DATA:CATALOG": SimAgilent33220AInstrument._data_catalog,
    "DATA:NVOLATILE:CATALOG": SimAgilent33220AInstrument._data_nvolatile_catalog,
    "DATA:NVOLATILE:FREE": SimAgilent33220AInstrument._data_nvolatile_free,
    "DATA:DELETE": SimAgilent33220AInstrument._data_delete,
    "DATA:DELETE:ALL": SimAgilent33220AInstrument._data_delete_all,
    "DATA:ATTRIBUTE:AVERAGE": SimAgilent33220AInstrument._data_attribute_average,
    "DATA:ATTRIBUTE:CFACTOR": SimAgilent33220AInstrument._data_attribute_cfactor,
    "DATA:ATTRIBUTE:POINTS": SimAgilent33220AInstrument._data_attribute_points,
    "DATA:ATTRIBUTE:PTPEAK": SimAgilent33220AInstrument._data_attribute_ptpeak,
    "FORMAT:BORDER": SimAgilent33220AInstrument._format_border,
    "MEMORY:STATE:VALID": SimAgilent33220AInstrument._memory_state_valid,
    "MEMORY:NSTATES": SimAgilent33220AInstrument._memory_nstates,
    "CAL": SimAgilent33220AInstrument._cal,
    "CAL:SECURE:STATE": SimAgilent33220AInstrument._cal_secure_state,
    "CAL:SECURE:CODE": SimAgilent33220AInstrument._cal_secure_code,
    "CAL:SETUP": SimAgilent33220AInstrument._cal_setup,
    "CAL:VALUE": SimAgilent33220AInstrument._cal_value,
    "CAL:COUNT": SimAgilent33220AInstrument._cal_count,
    "CAL:STRING": SimAgilent33220AInstrument._cal_string,
    "SYSTEM:COMMUNICATE:GPIB:ADDRESS": SimAgilent33220AInstrument._system_comm_gpib_address,
    "SYSTEM:COMMUNICATE:LAN:AUTOIP": SimAgilent33220AInstrument._system_comm_lan_autoip,
    "SYSTEM:COMMUNICATE:LAN:IPADDRESS": SimAgilent33220AInstrument._system_comm_lan_ipaddress,
    "SYSTEM:COMMUNICATE:LAN:LIPADDRESS": SimAgilent33220AInstrument._system_comm_lan_lipaddress,
    "SYSTEM:COMMUNICATE:LAN:MAC": SimAgilent33220AInstrument._system_comm_lan_mac,
    "SYSTEM:COMMUNICATE:LAN:MEDIASENSE": SimAgilent33220AInstrument._system_comm_lan_mediasense,
    "SYSTEM:COMMUNICATE:LAN:NETBIOS": SimAgilent33220AInstrument._system_comm_lan_netbios,
    "SYSTEM:COMMUNICATE:LAN:TELNET:PROMPT": SimAgilent33220AInstrument._system_comm_lan_telnet_prompt,
    "SYSTEM:COMMUNICATE:LAN:TELNET:WMESSAGE": SimAgilent33220AInstrument._system_comm_lan_telnet_wmessage,
}
