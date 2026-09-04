"""Deterministic in-process Agilent 34411A simulator.

Implements the command subset the core driver actually issues (task doc
§2/§13), as a text-in/bytes-out dispatcher so the driver's real SCPI
strings are exercised exactly as they would be against hardware.

Unlike ``agilent33220a``'s simulator, this instrument has no ``*LRN?``
equivalent (confirmed absent from both source documents during Gate 1
research) — state save/restore is native ``*SAV``/``*RCL`` against an
in-memory snapshot, not a host-replayed concatenated command string. No
``;``/``:`` concatenated-command dispatch is needed here.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import ClassVar

_IDN = "Agilent Technologies,34411A,SIM00001,2.35-2.35-2.35-46-09"

# Function tokens accepted by FUNCtion "<function>", and the config-key each
# one maps to (None for continuity/diode, which have no configuration).
_FUNCTION_TO_CONFIG_KEY = {
    "VOLT": "VOLTAGE",
    "VOLT:AC": "VOLTAGE:AC",
    "CURR": "CURRENT",
    "CURR:AC": "CURRENT:AC",
    "RES": "RESISTANCE",
    "FRES": "FRESISTANCE",
    "FREQ": "FREQUENCY",
    "PER": "PERIOD",
    "CAP": "CAPACITANCE",
    "TEMP": "TEMPERATURE",
    "CONT": None,
    "DIOD": None,
}

# Per-function default simulated reading value (task §13's "deterministic,
# configurable measurement value per function" requirement).
_DEFAULT_READING = {
    "VOLTAGE": 1.234567,
    "VOLTAGE:AC": 1.0,
    "CURRENT": 0.001234,
    "CURRENT:AC": 0.001,
    "RESISTANCE": 1000.0,
    "FRESISTANCE": 1000.0,
    "FREQUENCY": 1000.0,
    "PERIOD": 0.001,
    "CAPACITANCE": 1e-8,
    "TEMPERATURE": 23.5,
    "CONTINUITY": 5.0,
    "DIODE": 0.6,
}

_OVERLOAD_VALUE = 9.9e37


@dataclass
class _FuncConfig:
    range_value: float = 10.0
    auto_range: bool = True
    nplc: float = 1.0
    aperture_s: float = 1.0
    integration_mode: str = "NPLC"
    auto_zero: str = "ON"
    offset_compensation: bool = False
    ac_filter_bandwidth: str = "20"
    input_impedance_auto: bool = False
    null_enabled: bool = False
    null_value: float = 0.0


@dataclass
class _TemperatureConfig:
    probe_type: str = "RTD"
    thermistor_type: str = "5000"
    rtd_reference_ohms: float = 100.0
    units: str = "C"


@dataclass
class _TriggerConfig:
    source: str = "IMM"
    level: float = 0.0
    slope: str = "POS"
    delay_s: float = 0.0
    delay_auto: bool = True
    trigger_count: float = 1.0
    sample_count: float = 1.0
    sample_source: str = "AUTO"
    sample_timer_s: float = 1.0
    pretrigger_sample_count: float = 0.0


@dataclass
class _CalibrationConfig:
    locked: bool = True
    security_code: str = "AT34411A"
    line_frequency: int = 50
    count: int = 3
    string: str = ""
    value: float = 0.0


@dataclass
class _LanConfig:
    dhcp: bool = True
    ip_address: str = "141.121.1.100"
    subnet_mask: str = "255.255.255.0"
    gateway: str = "141.121.1.1"
    dns: str = "0.0.0.0"
    hostname: str = "A-34411A-00001"
    domain: str = ""
    auto_ip: bool = True
    ddns: bool = True
    keepalive_s: float = 3600.0
    mdns: bool = True
    netbios: bool = True
    telnet_prompt: str = "SCPI> "
    telnet_welcome: str = ""
    history: str = ""


@dataclass
class _MathConfig:
    function: str = "AVER"
    state: bool = False
    db_reference: float = 0.0
    dbm_reference: float = 600.0
    limit_lower: float = 0.0
    limit_upper: float = 0.0
    statistics_readings: list = field(default_factory=list)


class SimAgilent34411AInstrument:
    """A small, deterministic stand-in for a real 34411A over VISA."""

    def __init__(self) -> None:
        self.language = "34411A"
        self.active_function = "VOLT"
        self.functions: dict[str, _FuncConfig] = {
            key: _FuncConfig() for key in set(_FUNCTION_TO_CONFIG_KEY.values()) if key
        }
        self.temperature = _TemperatureConfig()
        self.trigger = _TriggerConfig()
        self.math = _MathConfig()
        self.beeper_enabled = True
        self.display_on = True
        self.display_text: dict[int, str] = {1: "", 2: ""}
        self.window2_feed = ""
        self.terminals = "FRON"
        self.gpib_address = 22
        self.interfaces_enabled = {"GPIB": True, "USB": True, "LAN": True}
        self.reading_memory: list[float] = []
        self.nonvolatile_memory: list[float] = []
        self.memory_slots: dict[int, dict] = {}
        self.memory_valid: set[int] = set()
        self.memory_names: dict[int, str] = {}
        self.memory_recall_auto = False
        self.memory_recall_select = 0
        self.readings: dict[str, float] = dict(_DEFAULT_READING)
        self.force_overload = False
        self.trigger_now_calls = 0
        self.calibration = _CalibrationConfig()
        self.lan = _LanConfig()
        self.lan_mac_address = "00:30:D3:12:34:56"
        self.force_calibration_failure = False
        self._events: list[tuple[int, str]] = []

    # -- public dispatch -------------------------------------------------

    def dispatch(self, command: str) -> bytes:
        command = command.strip()
        if not command:
            return b""

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

    def _push_event(self, code: int, message: str) -> None:
        self._events.append((code, message))

    @staticmethod
    def _resolve_value(rest: str, *, minimum: float, maximum: float) -> float:
        token = rest.strip().upper()
        if token in ("MIN", "MINIMUM"):
            return minimum
        if token in ("MAX", "MAXIMUM"):
            return maximum
        if token in ("DEF", "DEFAULT"):
            return (minimum + maximum) / 2
        return float(rest)

    def _current_config_key(self) -> str | None:
        return _FUNCTION_TO_CONFIG_KEY[self.active_function]

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
        return b"+0"

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

    def _trg(self, _rest: str, _is_query: bool) -> bytes:
        return self._trigger_now("", False)

    def _sav(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        snapshot = {
            "functions": copy.deepcopy(self.functions),
            "active_function": self.active_function,
            "temperature": copy.deepcopy(self.temperature),
            "trigger": copy.deepcopy(self.trigger),
        }
        self.memory_slots[slot] = snapshot
        self.memory_valid.add(slot)
        self.memory_names.setdefault(slot, f"STATE_{slot}")
        return b""

    def _rcl(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        if slot not in self.memory_valid:
            self._push_event(-224, f"Illegal parameter value;memory state {slot} is empty")
            return b""
        snapshot = self.memory_slots[slot]
        self.functions = copy.deepcopy(snapshot["functions"])
        self.active_function = snapshot["active_function"]
        self.temperature = copy.deepcopy(snapshot["temperature"])
        self.trigger = copy.deepcopy(snapshot["trigger"])
        return b""

    # -- system/utility ----------------------------------------------------

    def _system_error(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b'+0,"No error"'
        code, message = self._events.pop(0)
        return f'{code},"{message}"'.encode("ascii")

    def _system_preset(self, _rest: str, _is_query: bool) -> bytes:
        self.__init__()  # type: ignore[misc]
        return b""

    def _system_beeper_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.beeper_enabled else b"0"
        self.beeper_enabled = rest.strip().upper() in ("ON", "1")
        return b""

    def _system_beeper(self, _rest: str, _is_query: bool) -> bytes:
        return b""

    def _system_language(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.language}"'.encode("ascii")
        self.language = rest.strip().strip('"')
        return b""

    def _system_communicate_enable(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            iface = rest.strip().upper()
            return b"1" if self.interfaces_enabled.get(iface, False) else b"0"
        state_token, _, iface = rest.partition(",")
        iface = iface.strip().upper()
        self.interfaces_enabled[iface] = state_token.strip().upper() in ("ON", "1")
        return b""

    def _system_communicate_gpib_address(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"+{self.gpib_address}".encode("ascii")
        self.gpib_address = int(rest)
        return b""

    def _display_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.display_on else b"0"
        self.display_on = rest.strip().upper() in ("ON", "1")
        return b""

    def _display_text_clear(self, _rest: str, _is_query: bool) -> bytes:
        self.display_text[1] = ""
        self.display_text[2] = ""
        return b""

    def _display_text_data(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.display_text[1]}"'.encode("ascii")
        self.display_text[1] = rest.strip().strip('"')
        return b""

    def _display_window2_text_feed(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.window2_feed}"'.encode("ascii")
        self.window2_feed = rest.strip().strip('"')
        return b""

    def _route_terminals(self, _rest: str, _is_query: bool) -> bytes:
        return self.terminals.encode("ascii")

    # -- function selection ------------------------------------------------

    def _function(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.active_function}"'.encode("ascii")
        token = rest.strip().strip('"').upper()
        if token not in _FUNCTION_TO_CONFIG_KEY:
            self._push_event(-224, f"Illegal parameter value;unknown function {token!r}")
            return b""
        self.active_function = token
        return b""

    def _unit_temperature(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.temperature.units.encode("ascii")
        self.temperature.units = rest.strip().upper()
        return b""

    def _temperature_transducer_type(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.temperature.probe_type.encode("ascii")
        self.temperature.probe_type = rest.strip().upper()
        return b""

    def _temperature_transducer_thermistor_type(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.temperature.thermistor_type.encode("ascii")
        self.temperature.thermistor_type = rest.strip()
        return b""

    def _temperature_transducer_rtd_resistance(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.temperature.rtd_reference_ohms:.6E}".encode("ascii")
        self.temperature.rtd_reference_ohms = self._resolve_value(rest, minimum=49.0, maximum=2100.0)
        return b""

    # -- per-function measurement configuration -----------------------------

    def _make_nplc_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return f"{cfg.nplc:.6E}".encode("ascii")
            cfg.nplc = self._resolve_value(rest, minimum=0.001, maximum=100.0)
            cfg.integration_mode = "NPLC"
            return b""

        return handler

    def _make_aperture_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return f"{cfg.aperture_s:.6E}".encode("ascii")
            cfg.aperture_s = self._resolve_value(rest, minimum=20e-6, maximum=1.0)
            cfg.integration_mode = "APERTURE"
            return b""

        return handler

    def _make_range_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return f"{cfg.range_value:.6E}".encode("ascii")
            cfg.range_value = self._resolve_value(rest, minimum=0.0, maximum=1.0e9)
            cfg.auto_range = False
            return b""

        return handler

    def _make_range_auto_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return b"1" if cfg.auto_range else b"0"
            token = rest.strip().upper()
            cfg.auto_range = token in ("ON", "1", "ONCE")
            return b""

        return handler

    def _make_zero_auto_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return b"1" if cfg.auto_zero in ("ON", "ONCE") else b"0"
            token = rest.strip().upper()
            cfg.auto_zero = {"1": "ON", "0": "OFF"}.get(token, token)
            return b""

        return handler

    def _make_ocomp_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return b"1" if cfg.offset_compensation else b"0"
            cfg.offset_compensation = rest.strip().upper() in ("ON", "1")
            return b""

        return handler

    def _make_bandwidth_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return cfg.ac_filter_bandwidth.encode("ascii")
            cfg.ac_filter_bandwidth = rest.strip()
            return b""

        return handler

    def _make_null_state_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return b"1" if cfg.null_enabled else b"0"
            cfg.null_enabled = rest.strip().upper() in ("ON", "1")
            return b""

        return handler

    def _make_null_value_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return f"{cfg.null_value:.6E}".encode("ascii")
            cfg.null_value = float(rest)
            return b""

        return handler

    def _make_impedance_auto_handler(key: str) -> Callable[[SimAgilent34411AInstrument, str, bool], bytes]:
        def handler(self: SimAgilent34411AInstrument, rest: str, is_query: bool) -> bytes:
            cfg = self.functions[key]
            if is_query:
                return b"1" if cfg.input_impedance_auto else b"0"
            cfg.input_impedance_auto = rest.strip().upper() in ("ON", "1")
            return b""

        return handler

    # -- math (CALCulate) ---------------------------------------------------

    def _calc_function(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.math.function.encode("ascii")
        self.math.function = rest.strip().upper()
        return b""

    def _calc_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.math.state else b"0"
        self.math.state = rest.strip().upper() in ("ON", "1")
        return b""

    def _calc_db_reference(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.math.db_reference:.6E}".encode("ascii")
        self.math.db_reference = float(rest)
        return b""

    def _calc_dbm_reference(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.math.dbm_reference:.6E}".encode("ascii")
        self.math.dbm_reference = float(rest)
        return b""

    def _calc_average_average(self, _rest: str, _is_query: bool) -> bytes:
        values = self.math.statistics_readings
        return f"{(sum(values) / len(values)) if values else 0.0:.6E}".encode("ascii")

    def _calc_average_minimum(self, _rest: str, _is_query: bool) -> bytes:
        values = self.math.statistics_readings
        return f"{min(values) if values else 0.0:.6E}".encode("ascii")

    def _calc_average_maximum(self, _rest: str, _is_query: bool) -> bytes:
        values = self.math.statistics_readings
        return f"{max(values) if values else 0.0:.6E}".encode("ascii")

    def _calc_average_ptpeak(self, _rest: str, _is_query: bool) -> bytes:
        values = self.math.statistics_readings
        return f"{(max(values) - min(values)) if values else 0.0:.6E}".encode("ascii")

    def _calc_average_sdeviation(self, _rest: str, _is_query: bool) -> bytes:
        values = self.math.statistics_readings
        if len(values) < 2:
            return b"0.0E0"
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        return f"{variance ** 0.5:.6E}".encode("ascii")

    def _calc_average_count(self, _rest: str, _is_query: bool) -> bytes:
        return str(len(self.math.statistics_readings)).encode("ascii")

    def _calc_average_clear(self, _rest: str, _is_query: bool) -> bytes:
        self.math.statistics_readings.clear()
        return b""

    def _calc_limit_lower(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.math.limit_lower:.6E}".encode("ascii")
        self.math.limit_lower = float(rest)
        return b""

    def _calc_limit_upper(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.math.limit_upper:.6E}".encode("ascii")
        self.math.limit_upper = float(rest)
        return b""

    # -- trigger / sample -----------------------------------------------------

    def _trigger_source(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.source.encode("ascii")
        self.trigger.source = rest.strip().upper()
        return b""

    def _trigger_level(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.level:.6E}".encode("ascii")
        self.trigger.level = float(rest)
        return b""

    def _trigger_slope(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.slope.encode("ascii")
        self.trigger.slope = rest.strip().upper()
        return b""

    def _trigger_count(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.trigger_count:.6E}".encode("ascii")
        token = rest.strip().upper()
        self.trigger.trigger_count = float("inf") if token in ("INF", "INFINITY") else float(rest)
        return b""

    def _trigger_delay(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.delay_s:.6E}".encode("ascii")
        self.trigger.delay_s = self._resolve_value(rest, minimum=0.0, maximum=3600.0)
        return b""

    def _trigger_delay_auto(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.trigger.delay_auto else b"0"
        self.trigger.delay_auto = rest.strip().upper() in ("ON", "1")
        return b""

    def _sample_count(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.sample_count:.6E}".encode("ascii")
        token = rest.strip().upper()
        self.trigger.sample_count = float("inf") if token in ("INF", "INFINITY") else float(rest)
        return b""

    def _sample_count_pretrigger(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.pretrigger_sample_count:.6E}".encode("ascii")
        self.trigger.pretrigger_sample_count = float(rest)
        return b""

    def _sample_source(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.trigger.sample_source.encode("ascii")
        self.trigger.sample_source = rest.strip().upper()
        return b""

    def _sample_timer(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.trigger.sample_timer_s:.6E}".encode("ascii")
        self.trigger.sample_timer_s = float(rest)
        return b""

    def _trigger_now(self, _rest: str, _is_query: bool) -> bytes:
        self.trigger_now_calls += 1
        self._take_readings()
        return b""

    def _abort(self, _rest: str, _is_query: bool) -> bytes:
        return b""

    def _initiate(self, _rest: str, _is_query: bool) -> bytes:
        self._take_readings()
        return b""

    def _take_readings(self) -> None:
        key = self._current_config_key()
        value = self.readings.get(key or self.active_function, 0.0)
        if self.force_overload:
            value = _OVERLOAD_VALUE
        count = self.trigger.sample_count
        count = 1 if count in (float("inf"), 0) else int(count)
        for _ in range(count):
            self.reading_memory.append(value)
            if self.math.state and self.math.function == "AVER" and value != _OVERLOAD_VALUE:
                self.math.statistics_readings.append(value)

    # -- reading / data memory -----------------------------------------------

    def _read(self, _rest: str, _is_query: bool) -> bytes:
        self.reading_memory = []
        self._take_readings()
        return self._format_readings(self.reading_memory)

    def _fetch(self, _rest: str, _is_query: bool) -> bytes:
        return self._format_readings(self.reading_memory)

    @staticmethod
    def _format_readings(values: list) -> bytes:
        if not values:
            return b""
        return ",".join(f"{v:.6E}" for v in values).encode("ascii")

    def _data_last(self, _rest: str, _is_query: bool) -> bytes:
        if not self.reading_memory:
            return b"+9.91000000E+37"
        return f"{self.reading_memory[-1]:.6E}".encode("ascii")

    def _data_points(self, rest: str, _is_query: bool) -> bytes:
        if rest.strip().upper() == "NVMEM":
            return str(len(self.nonvolatile_memory)).encode("ascii")
        return str(len(self.reading_memory)).encode("ascii")

    def _data_remove(self, rest: str, _is_query: bool) -> bytes:
        count = int(rest)
        popped, self.reading_memory = self.reading_memory[:count], self.reading_memory[count:]
        return self._format_readings(popped)

    def _data_copy(self, rest: str, _is_query: bool) -> bytes:
        parts = [p.strip() for p in rest.split(",")]
        if len(parts) >= 1 and parts[0].upper() == "NVMEM":
            self.nonvolatile_memory.extend(self.reading_memory)
        return b""

    def _data_data(self, rest: str, _is_query: bool) -> bytes:
        if rest.strip().upper() == "NVMEM":
            return self._format_readings(self.nonvolatile_memory)
        return b""

    def _data_delete(self, rest: str, _is_query: bool) -> bytes:
        if rest.strip().upper() == "NVMEM":
            self.nonvolatile_memory.clear()
        return b""

    def _r(self, rest: str, _is_query: bool) -> bytes:
        count = int(rest) if rest.strip() else len(self.nonvolatile_memory)
        popped = self.nonvolatile_memory[:count]
        self.nonvolatile_memory = self.nonvolatile_memory[count:]
        return self._format_readings(popped)

    # -- instrument memory (MEMory subsystem) --------------------------------

    def _memory_nstates(self, _rest: str, _is_query: bool) -> bytes:
        return b"5"

    def _memory_state_catalog(self, _rest: str, _is_query: bool) -> bytes:
        return ",".join(str(slot) for slot in sorted(self.memory_valid)).encode("ascii")

    def _memory_state_delete(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        self.memory_valid.discard(slot)
        self.memory_slots.pop(slot, None)
        self.memory_names.pop(slot, None)
        return b""

    def _memory_state_delete_all(self, _rest: str, _is_query: bool) -> bytes:
        self.memory_valid.clear()
        self.memory_slots.clear()
        self.memory_names.clear()
        return b""

    def _memory_state_name(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            slot = int(rest)
            return f'"{self.memory_names.get(slot, "")}"'.encode("ascii")
        slot_token, _, name = rest.partition(",")
        slot = int(slot_token.strip())
        self.memory_names[slot] = name.strip().strip('"') if name.strip() else f"STATE_{slot}"
        return b""

    def _memory_state_recall_auto(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.memory_recall_auto else b"0"
        self.memory_recall_auto = rest.strip().upper() in ("ON", "1")
        return b""

    def _memory_state_recall_select(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.memory_recall_select).encode("ascii")
        self.memory_recall_select = int(rest)
        return b""

    def _memory_state_valid(self, rest: str, _is_query: bool) -> bytes:
        slot = int(rest)
        return b"1" if slot in self.memory_valid else b"0"

    # -- calibration (CALibration subsystem) ----------------------------------

    def _calibration(self, _rest: str, _is_query: bool) -> bytes:
        """CALibration[:ALL]? — sent as ``CALibration?``. Query-only, runs a full cal."""
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
            return b"1"
        self.calibration.count += 1
        return b"1" if self.force_calibration_failure else b"0"

    def _calibration_adc(self, _rest: str, _is_query: bool) -> bytes:
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
            return b"+9.9E+37"
        return b"+9.9E+37" if self.force_calibration_failure else b"+1.0E-06"

    def _calibration_count(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.calibration.count).encode("ascii")

    def _calibration_lfrequency(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.calibration.line_frequency).encode("ascii")
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
            return b""
        self.calibration.line_frequency = int(float(rest))
        return b""

    def _calibration_lfrequency_actual(self, _rest: str, _is_query: bool) -> bytes:
        return f"{float(self.calibration.line_frequency):.6E}".encode("ascii")

    def _calibration_secure_state(self, rest: str, is_query: bool) -> bytes:
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
                self._push_event(-224, "Illegal parameter value;invalid security code")
                return b""
            self.calibration.locked = False
            return b""
        self._push_event(-224, f"Illegal parameter value;{rest!r}")
        return b""

    def _calibration_secure_code(self, rest: str, _is_query: bool) -> bytes:
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
            return b""
        self.calibration.security_code = rest.strip()
        return b""

    def _calibration_store(self, _rest: str, _is_query: bool) -> bytes:
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
        return b""

    def _calibration_string(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.calibration.string}"'.encode("ascii")
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
            return b""
        text = rest.strip()
        if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
            text = text[1:-1]
        self.calibration.string = text[:40]
        return b""

    def _calibration_value(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.calibration.value:.6E}".encode("ascii")
        if self.calibration.locked:
            self._push_event(-221, "Settings conflict;calibration is secured")
            return b""
        self.calibration.value = float(rest)
        return b""

    # -- LAN configuration (SYSTem:COMMunicate:LAN subsystem) ----------------

    def _lan_dhcp(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.lan.dhcp else b"0"
        self.lan.dhcp = rest.strip().upper() in ("ON", "1")
        return b""

    def _lan_ip_address(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.ip_address}"'.encode("ascii")
        self.lan.ip_address = rest.strip().strip('"')
        return b""

    def _lan_subnet_mask(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.subnet_mask}"'.encode("ascii")
        self.lan.subnet_mask = rest.strip().strip('"')
        return b""

    def _lan_gateway(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.gateway}"'.encode("ascii")
        self.lan.gateway = rest.strip().strip('"')
        return b""

    def _lan_dns(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.dns}"'.encode("ascii")
        self.lan.dns = rest.strip().strip('"')
        return b""

    def _lan_hostname(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.hostname}"'.encode("ascii")
        self.lan.hostname = rest.strip().strip('"')
        return b""

    def _lan_domain(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.domain}"'.encode("ascii")
        self.lan.domain = rest.strip().strip('"')
        return b""

    def _lan_autoip_state(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.lan.auto_ip else b"0"
        self.lan.auto_ip = rest.strip().upper() in ("ON", "1")
        return b""

    def _lan_ddns(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.lan.ddns else b"0"
        self.lan.ddns = rest.strip().upper() in ("ON", "1")
        return b""

    def _lan_keepalive(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.lan.keepalive_s:.6E}".encode("ascii")
        self.lan.keepalive_s = float(rest)
        return b""

    def _lan_lipaddress(self, _rest: str, _is_query: bool) -> bytes:
        return f'"{self.lan.ip_address}"'.encode("ascii")

    def _lan_mac(self, _rest: str, _is_query: bool) -> bytes:
        return f'"{self.lan_mac_address}"'.encode("ascii")

    def _lan_bstatus(self, _rest: str, _is_query: bool) -> bytes:
        return b'"CONNECTED"'

    def _lan_control_status(self, _rest: str, _is_query: bool) -> bytes:
        return b'"CONNECTED"'

    def _lan_mediasense(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.lan.mdns else b"0"
        self.lan.mdns = rest.strip().upper() in ("ON", "1")
        return b""

    def _lan_netbios(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.lan.netbios else b"0"
        self.lan.netbios = rest.strip().upper() in ("ON", "1")
        return b""

    def _lan_telnet_prompt(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.telnet_prompt}"'.encode("ascii")
        self.lan.telnet_prompt = rest.strip().strip('"')
        return b""

    def _lan_telnet_wmessage(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.telnet_welcome}"'.encode("ascii")
        self.lan.telnet_welcome = rest.strip().strip('"')
        return b""

    def _lan_history_clear(self, _rest: str, _is_query: bool) -> bytes:
        self.lan.history = ""
        return b""

    def _lan_history(self, _rest: str, _is_query: bool) -> bytes:
        return f'"{self.lan.history}"'.encode("ascii")

    # -- routing table --------------------------------------------------------

    _ROUTES: ClassVar[dict[str, Callable]]


_ROUTES: dict[str, Callable] = {
    "*IDN": SimAgilent34411AInstrument._idn,
    "*CLS": SimAgilent34411AInstrument._cls,
    "*RST": SimAgilent34411AInstrument._rst,
    "*TST": SimAgilent34411AInstrument._tst,
    "*OPC": SimAgilent34411AInstrument._opc,
    "*WAI": SimAgilent34411AInstrument._wai,
    "*PSC": SimAgilent34411AInstrument._psc,
    "*STB": SimAgilent34411AInstrument._stb,
    "*SRE": SimAgilent34411AInstrument._sre,
    "*ESR": SimAgilent34411AInstrument._esr,
    "*ESE": SimAgilent34411AInstrument._ese,
    "*TRG": SimAgilent34411AInstrument._trg,
    "*SAV": SimAgilent34411AInstrument._sav,
    "*RCL": SimAgilent34411AInstrument._rcl,
    "SYSTEM:ERROR": SimAgilent34411AInstrument._system_error,
    "SYSTEM:PRESET": SimAgilent34411AInstrument._system_preset,
    "SYSTEM:BEEPER:STATE": SimAgilent34411AInstrument._system_beeper_state,
    "SYSTEM:BEEPER": SimAgilent34411AInstrument._system_beeper,
    "SYSTEM:LANGUAGE": SimAgilent34411AInstrument._system_language,
    "SYSTEM:COMMUNICATE:ENABLE": SimAgilent34411AInstrument._system_communicate_enable,
    "SYSTEM:COMMUNICATE:GPIB:ADDRESS": SimAgilent34411AInstrument._system_communicate_gpib_address,
    "DISPLAY": SimAgilent34411AInstrument._display_state,
    "DISPLAY:TEXT:CLEAR": SimAgilent34411AInstrument._display_text_clear,
    "DISPLAY:TEXT": SimAgilent34411AInstrument._display_text_data,
    "DISPLAY:WINDOW2:TEXT:FEED": SimAgilent34411AInstrument._display_window2_text_feed,
    "ROUTE:TERMINALS": SimAgilent34411AInstrument._route_terminals,
    "FUNCTION": SimAgilent34411AInstrument._function,
    "UNIT:TEMPERATURE": SimAgilent34411AInstrument._unit_temperature,
    "TEMPERATURE:TRANSDUCER:TYPE": SimAgilent34411AInstrument._temperature_transducer_type,
    "TEMPERATURE:TRANSDUCER:THERMISTOR:TYPE":
        SimAgilent34411AInstrument._temperature_transducer_thermistor_type,
    "TEMPERATURE:TRANSDUCER:RTD:RESISTANCE":
        SimAgilent34411AInstrument._temperature_transducer_rtd_resistance,
    "TEMPERATURE:TRANSDUCER:FRTD:RESISTANCE":
        SimAgilent34411AInstrument._temperature_transducer_rtd_resistance,
    "CALCULATE:FUNCTION": SimAgilent34411AInstrument._calc_function,
    "CALCULATE:STATE": SimAgilent34411AInstrument._calc_state,
    "CALCULATE:DB:REFERENCE": SimAgilent34411AInstrument._calc_db_reference,
    "CALCULATE:DBM:REFERENCE": SimAgilent34411AInstrument._calc_dbm_reference,
    "CALCULATE:AVERAGE:AVERAGE": SimAgilent34411AInstrument._calc_average_average,
    "CALCULATE:AVERAGE:MINIMUM": SimAgilent34411AInstrument._calc_average_minimum,
    "CALCULATE:AVERAGE:MAXIMUM": SimAgilent34411AInstrument._calc_average_maximum,
    "CALCULATE:AVERAGE:PTPEAK": SimAgilent34411AInstrument._calc_average_ptpeak,
    "CALCULATE:AVERAGE:SDEVIATION": SimAgilent34411AInstrument._calc_average_sdeviation,
    "CALCULATE:AVERAGE:COUNT": SimAgilent34411AInstrument._calc_average_count,
    "CALCULATE:AVERAGE:CLEAR": SimAgilent34411AInstrument._calc_average_clear,
    "CALCULATE:LIMIT:LOWER": SimAgilent34411AInstrument._calc_limit_lower,
    "CALCULATE:LIMIT:UPPER": SimAgilent34411AInstrument._calc_limit_upper,
    "TRIGGER:SOURCE": SimAgilent34411AInstrument._trigger_source,
    "TRIGGER:LEVEL": SimAgilent34411AInstrument._trigger_level,
    "TRIGGER:SLOPE": SimAgilent34411AInstrument._trigger_slope,
    "TRIGGER:COUNT": SimAgilent34411AInstrument._trigger_count,
    "TRIGGER:DELAY": SimAgilent34411AInstrument._trigger_delay,
    "TRIGGER:DELAY:AUTO": SimAgilent34411AInstrument._trigger_delay_auto,
    "SAMPLE:COUNT": SimAgilent34411AInstrument._sample_count,
    "SAMPLE:COUNT:PRETRIGGER": SimAgilent34411AInstrument._sample_count_pretrigger,
    "SAMPLE:SOURCE": SimAgilent34411AInstrument._sample_source,
    "SAMPLE:TIMER": SimAgilent34411AInstrument._sample_timer,
    "ABORT": SimAgilent34411AInstrument._abort,
    "INITIATE": SimAgilent34411AInstrument._initiate,
    "INITIATE:IMMEDIATE": SimAgilent34411AInstrument._initiate,
    "READ": SimAgilent34411AInstrument._read,
    "FETCH": SimAgilent34411AInstrument._fetch,
    "DATA:LAST": SimAgilent34411AInstrument._data_last,
    "DATA:POINTS": SimAgilent34411AInstrument._data_points,
    "DATA:REMOVE": SimAgilent34411AInstrument._data_remove,
    "DATA:COPY": SimAgilent34411AInstrument._data_copy,
    "DATA:DATA": SimAgilent34411AInstrument._data_data,
    "DATA:DELETE": SimAgilent34411AInstrument._data_delete,
    "R": SimAgilent34411AInstrument._r,
    "MEMORY:NSTATES": SimAgilent34411AInstrument._memory_nstates,
    "MEMORY:STATE:CATALOG": SimAgilent34411AInstrument._memory_state_catalog,
    "MEMORY:STATE:DELETE": SimAgilent34411AInstrument._memory_state_delete,
    "MEMORY:STATE:DELETE:ALL": SimAgilent34411AInstrument._memory_state_delete_all,
    "MEMORY:STATE:NAME": SimAgilent34411AInstrument._memory_state_name,
    "MEMORY:STATE:RECALL:AUTO": SimAgilent34411AInstrument._memory_state_recall_auto,
    "MEMORY:STATE:RECALL:SELECT": SimAgilent34411AInstrument._memory_state_recall_select,
    "MEMORY:STATE:VALID": SimAgilent34411AInstrument._memory_state_valid,
    "CALIBRATION": SimAgilent34411AInstrument._calibration,
    "CALIBRATION:ADC": SimAgilent34411AInstrument._calibration_adc,
    "CALIBRATION:COUNT": SimAgilent34411AInstrument._calibration_count,
    "CALIBRATION:LFREQUENCY": SimAgilent34411AInstrument._calibration_lfrequency,
    "CALIBRATION:LFREQUENCY:ACTUAL": SimAgilent34411AInstrument._calibration_lfrequency_actual,
    "CALIBRATION:SECURE:STATE": SimAgilent34411AInstrument._calibration_secure_state,
    "CALIBRATION:SECURE:CODE": SimAgilent34411AInstrument._calibration_secure_code,
    "CALIBRATION:STORE": SimAgilent34411AInstrument._calibration_store,
    "CALIBRATION:STRING": SimAgilent34411AInstrument._calibration_string,
    "CALIBRATION:VALUE": SimAgilent34411AInstrument._calibration_value,
    "SYSTEM:COMMUNICATE:LAN:DHCP": SimAgilent34411AInstrument._lan_dhcp,
    "SYSTEM:COMMUNICATE:LAN:IPADDRESS": SimAgilent34411AInstrument._lan_ip_address,
    "SYSTEM:COMMUNICATE:LAN:SMASK": SimAgilent34411AInstrument._lan_subnet_mask,
    "SYSTEM:COMMUNICATE:LAN:GATEWAY": SimAgilent34411AInstrument._lan_gateway,
    "SYSTEM:COMMUNICATE:LAN:DNS": SimAgilent34411AInstrument._lan_dns,
    "SYSTEM:COMMUNICATE:LAN:HOSTNAME": SimAgilent34411AInstrument._lan_hostname,
    "SYSTEM:COMMUNICATE:LAN:DOMAIN": SimAgilent34411AInstrument._lan_domain,
    "SYSTEM:COMMUNICATE:LAN:AUTOIP:STATE": SimAgilent34411AInstrument._lan_autoip_state,
    "SYSTEM:COMMUNICATE:LAN:DDNS": SimAgilent34411AInstrument._lan_ddns,
    "SYSTEM:COMMUNICATE:LAN:KEEPALIVE": SimAgilent34411AInstrument._lan_keepalive,
    "SYSTEM:COMMUNICATE:LAN:LIPADDRESS": SimAgilent34411AInstrument._lan_lipaddress,
    "SYSTEM:COMMUNICATE:LAN:MAC": SimAgilent34411AInstrument._lan_mac,
    "SYSTEM:COMMUNICATE:LAN:BSTATUS": SimAgilent34411AInstrument._lan_bstatus,
    "SYSTEM:COMMUNICATE:LAN:CONTROL": SimAgilent34411AInstrument._lan_control_status,
    "SYSTEM:COMMUNICATE:LAN:MEDIASENSE": SimAgilent34411AInstrument._lan_mediasense,
    "SYSTEM:COMMUNICATE:LAN:NETBIOS": SimAgilent34411AInstrument._lan_netbios,
    "SYSTEM:COMMUNICATE:LAN:TELNET:PROMPT": SimAgilent34411AInstrument._lan_telnet_prompt,
    "SYSTEM:COMMUNICATE:LAN:TELNET:WMESSAGE": SimAgilent34411AInstrument._lan_telnet_wmessage,
    "SYSTEM:COMMUNICATE:LAN:HISTORY:CLEAR": SimAgilent34411AInstrument._lan_history_clear,
    "SYSTEM:COMMUNICATE:LAN:HISTORY": SimAgilent34411AInstrument._lan_history,
}

# Per-function measurement configuration routes, generated rather than
# hand-enumerated (task §5) — one entry per (subsystem, parameter) pair
# that applies to that subsystem, per the confirmed Command Quick Reference.
_NPLC_APERTURE_FUNCTIONS = ("VOLTAGE", "CURRENT", "RESISTANCE", "FRESISTANCE", "TEMPERATURE")
_APERTURE_ONLY_FUNCTIONS = ("FREQUENCY", "PERIOD")  # gate time; no NPLC
_RANGE_FUNCTIONS = ("VOLTAGE", "VOLTAGE:AC", "CURRENT", "CURRENT:AC", "RESISTANCE",
                     "FRESISTANCE", "CAPACITANCE")
_ZERO_AUTO_FUNCTIONS = ("VOLTAGE", "CURRENT", "RESISTANCE", "TEMPERATURE")  # not FRESISTANCE
_OCOMP_FUNCTIONS = ("RESISTANCE", "FRESISTANCE", "TEMPERATURE")
_BANDWIDTH_FUNCTIONS = ("VOLTAGE:AC", "CURRENT:AC")
_NULL_FUNCTIONS = ("VOLTAGE", "VOLTAGE:AC", "CURRENT", "CURRENT:AC", "RESISTANCE",
                    "FRESISTANCE", "FREQUENCY", "PERIOD", "CAPACITANCE", "TEMPERATURE")

for _key in _NPLC_APERTURE_FUNCTIONS:
    _ROUTES[f"{_key}:NPLC"] = SimAgilent34411AInstrument._make_nplc_handler(_key)
    _ROUTES[f"{_key}:APERTURE"] = SimAgilent34411AInstrument._make_aperture_handler(_key)
for _key in _APERTURE_ONLY_FUNCTIONS:
    _ROUTES[f"{_key}:APERTURE"] = SimAgilent34411AInstrument._make_aperture_handler(_key)
for _key in _RANGE_FUNCTIONS:
    _ROUTES[f"{_key}:RANGE"] = SimAgilent34411AInstrument._make_range_handler(_key)
    _ROUTES[f"{_key}:RANGE:AUTO"] = SimAgilent34411AInstrument._make_range_auto_handler(_key)
for _key in _APERTURE_ONLY_FUNCTIONS:
    _ROUTES[f"{_key}:VOLTAGE:RANGE"] = SimAgilent34411AInstrument._make_range_handler(_key)
    _ROUTES[f"{_key}:VOLTAGE:RANGE:AUTO"] = SimAgilent34411AInstrument._make_range_auto_handler(_key)
for _key in _ZERO_AUTO_FUNCTIONS:
    _ROUTES[f"{_key}:ZERO:AUTO"] = SimAgilent34411AInstrument._make_zero_auto_handler(_key)
for _key in _OCOMP_FUNCTIONS:
    _ROUTES[f"{_key}:OCOMPENSATED"] = SimAgilent34411AInstrument._make_ocomp_handler(_key)
for _key in _BANDWIDTH_FUNCTIONS:
    _ROUTES[f"{_key}:BANDWIDTH"] = SimAgilent34411AInstrument._make_bandwidth_handler(_key)
for _key in _NULL_FUNCTIONS:
    _ROUTES[f"{_key}:NULL"] = SimAgilent34411AInstrument._make_null_state_handler(_key)
    _ROUTES[f"{_key}:NULL:VALUE"] = SimAgilent34411AInstrument._make_null_value_handler(_key)
_ROUTES["VOLTAGE:IMPEDANCE:AUTO"] = SimAgilent34411AInstrument._make_impedance_auto_handler("VOLTAGE")

SimAgilent34411AInstrument._ROUTES = _ROUTES
