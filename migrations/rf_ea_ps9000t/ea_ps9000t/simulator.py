"""Deterministic in-process EA-PS 9000 T simulator.

Implements the command subset the core driver actually issues (task doc
§2/§11), as a text-in/bytes-out dispatcher so the driver's real SCPI
strings are exercised exactly as they would be against hardware.

No ``*LRN?`` equivalent exists for this series (presets/recall is confirmed
PSI-5000-A-only, not PST — task §2), so, like ``agilent34411a``'s
simulator, no ``;``/``:`` concatenated-command replay is needed here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

_IDN_FIXED = "EA-Elektro-Automatik,PS 9080-60 T,SIM00001,3.06"

_NOMINAL_VOLTAGE = 80.0
_NOMINAL_CURRENT = 60.0
_NOMINAL_POWER = 1500.0
_DEVICE_CLASS = "1"  # source, per SYSTem:DEVice:CLASs? (task §2)


@dataclass
class _SetValues:
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0


@dataclass
class _Protection:
    overvoltage: float = _NOMINAL_VOLTAGE * 1.1
    overcurrent: float = _NOMINAL_CURRENT * 1.1
    overpower: float = _NOMINAL_POWER * 1.1


@dataclass
class _Limits:
    voltage_low: float = 0.0
    voltage_high: float = _NOMINAL_VOLTAGE * 1.02
    current_low: float = 0.0
    current_high: float = _NOMINAL_CURRENT * 1.02
    power_high: float = _NOMINAL_POWER * 1.02


@dataclass
class _DeviceConfig:
    power_stage_after_remote: str = "AUTO"
    output_restore: str = "AUTO"
    user_text: str = ""
    communication_timeout_ms: int = 5
    alarm_action_pfail: str = "AUTO"
    alarm_action_otemperature: str = "AUTO"


@dataclass
class _AlarmCounters:
    overvoltage: int = 0
    overtemperature: int = 0
    overpower: int = 0
    overcurrent: int = 0
    power_fail: int = 0


@dataclass
class _LanConfig:
    """SYSTem:COMMunicate:LAN:* state (Gate 3). Defaults match the documented
    factory defaults except IP-ish fields, which are seeded with plausible
    private-range placeholders since the source document's own stated default
    IP is a likely typo (see README.md "Known documentation discrepancy")."""

    dhcp: str = "OFF"
    address: str = "192.168.0.2"
    subnet_mask: str = "255.255.255.0"
    gateway: str = "192.168.0.1"
    hostname: str = ""
    domain: str = ""
    dns1: str = ""
    dns2: str = ""
    control_port: int = 5025
    keepalive: str = "OFF"
    timeout_s: int = 5
    mac: str = "00:80:A3:00:00:01"


@dataclass
class _AnalogConfig:
    """SYSTem:CONFig:ANAlog:* state (Gate 3)."""

    reference_v: int = 10
    remsb_level: str = "NORMAL"
    remsb_action: str = "OFF"


class SimEaPs9000TInstrument:
    """A small, deterministic stand-in for a real PS 9000 T over VISA."""

    def __init__(self) -> None:
        self.lock_owner = "NONE"
        self.force_lock_refusal = False
        self.output_enabled = False
        self.set_values = _SetValues()
        self.protection = _Protection()
        self.limits = _Limits()
        self.config = _DeviceConfig()
        self.lan = _LanConfig()
        self.analog = _AnalogConfig()
        self.alarm_counters = _AlarmCounters()
        self.measured = _SetValues()  # deterministic "next reading" per quantity
        self.force_data_out_of_range = False
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
            self._push_event(-100, f"Command unknown;{command}")
            return b""
        return handler(self, rest, is_query)

    def _push_event(self, code: int, message: str) -> None:
        self._events.append((code, message))

    def _require_remote(self) -> bool:
        """Returns True if a write is allowed; pushes -201 and returns False otherwise."""

        if self.lock_owner != "REMOTE":
            self._push_event(-201, "Invalid while in local")
            return False
        return True

    @staticmethod
    def _resolve_value(rest: str, *, minimum: float, maximum: float) -> float:
        token = rest.strip().upper()
        if token == "MIN":
            return minimum
        if token == "MAX":
            return maximum
        return float(rest.split()[0]) if rest.strip() else minimum

    # -- standard/common commands ----------------------------------------

    def _idn(self, _rest: str, _is_query: bool) -> bytes:
        text = f",{self.config.user_text}" if self.config.user_text else ""
        return f"{_IDN_FIXED}{text}".encode("ascii")

    def _cls(self, _rest: str, _is_query: bool) -> bytes:
        self._events.clear()
        return b""

    def _rst(self, _rest: str, _is_query: bool) -> bytes:
        self.lock_owner = "REMOTE"  # *RST switches to remote control, per task §2
        self.output_enabled = False
        self._events.clear()
        self.set_values = _SetValues()
        return b""

    def _stb(self, _rest: str, _is_query: bool) -> bytes:
        return b"4" if self._events else b"0"

    def _opc(self, _rest: str, _is_query: bool) -> bytes:
        """The simulator processes every command synchronously, so there is never a
        pending overlapped operation to wait on — always reports complete."""

        return b"1"

    # -- remote control lock -----------------------------------------------

    def _system_lock(self, rest: str, _is_query: bool) -> bytes:
        token = rest.strip().upper()
        requesting_on = token in ("ON", "1")
        if requesting_on:
            if self.force_lock_refusal:
                self._push_event(-200, "Execution error;remote control refused")
                return b""
            self.lock_owner = "REMOTE"
        else:
            self.lock_owner = "NONE"
        return b""

    def _system_lock_owner(self, _rest: str, _is_query: bool) -> bytes:
        return self.lock_owner.encode("ascii")

    # -- output --------------------------------------------------------------

    def _output(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return b"1" if self.output_enabled else b"0"
        if not self._require_remote():
            return b""
        self.output_enabled = rest.strip().upper() in ("ON", "1")
        return b""

    # -- set values ------------------------------------------------------------

    def _voltage(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.set_values.voltage:.4f} V".encode("ascii")
        if not self._require_remote():
            return b""
        value = self._resolve_value(rest, minimum=0.0, maximum=_NOMINAL_VOLTAGE * 1.02)
        if self.force_data_out_of_range or not (self.limits.voltage_low <= value <= self.limits.voltage_high):
            self._push_event(-222, "Data out of range")
            return b""
        self.set_values.voltage = value
        return b""

    def _current(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.set_values.current:.4f} A".encode("ascii")
        if not self._require_remote():
            return b""
        value = self._resolve_value(rest, minimum=0.0, maximum=_NOMINAL_CURRENT * 1.02)
        if self.force_data_out_of_range or not (self.limits.current_low <= value <= self.limits.current_high):
            self._push_event(-222, "Data out of range")
            return b""
        self.set_values.current = value
        return b""

    def _power(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.set_values.power:.4f} W".encode("ascii")
        if not self._require_remote():
            return b""
        value = self._resolve_value(rest, minimum=0.0, maximum=_NOMINAL_POWER * 1.02)
        if self.force_data_out_of_range or value > self.limits.power_high:
            self._push_event(-222, "Data out of range")
            return b""
        self.set_values.power = value
        return b""

    # -- protection thresholds --------------------------------------------------

    def _voltage_protection(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.protection.overvoltage:.4f} V".encode("ascii")
        if not self._require_remote():
            return b""
        self.protection.overvoltage = self._resolve_value(rest, minimum=0.0, maximum=_NOMINAL_VOLTAGE * 1.1)
        return b""

    def _current_protection(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.protection.overcurrent:.4f} A".encode("ascii")
        if not self._require_remote():
            return b""
        self.protection.overcurrent = self._resolve_value(rest, minimum=0.0, maximum=_NOMINAL_CURRENT * 1.1)
        return b""

    def _power_protection(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.protection.overpower:.4f} W".encode("ascii")
        if not self._require_remote():
            return b""
        self.protection.overpower = self._resolve_value(rest, minimum=0.0, maximum=_NOMINAL_POWER * 1.1)
        return b""

    # -- adjustment limits ----------------------------------------------------

    def _voltage_limit_low(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.limits.voltage_low:.4f} V".encode("ascii")
        if not self._require_remote():
            return b""
        self.limits.voltage_low = float(rest)
        return b""

    def _voltage_limit_high(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.limits.voltage_high:.4f} V".encode("ascii")
        if not self._require_remote():
            return b""
        self.limits.voltage_high = float(rest)
        return b""

    def _current_limit_low(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.limits.current_low:.4f} A".encode("ascii")
        if not self._require_remote():
            return b""
        self.limits.current_low = float(rest)
        return b""

    def _current_limit_high(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.limits.current_high:.4f} A".encode("ascii")
        if not self._require_remote():
            return b""
        self.limits.current_high = float(rest)
        return b""

    def _power_limit_high(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f"{self.limits.power_high:.4f} W".encode("ascii")
        if not self._require_remote():
            return b""
        self.limits.power_high = float(rest)
        return b""

    # -- measuring -------------------------------------------------------------

    def _measure_voltage(self, _rest: str, _is_query: bool) -> bytes:
        return f"{self.measured.voltage:.4f} V".encode("ascii")

    def _measure_current(self, _rest: str, _is_query: bool) -> bytes:
        return f"{self.measured.current:.4f} A".encode("ascii")

    def _measure_power(self, _rest: str, _is_query: bool) -> bytes:
        return f"{self.measured.power:.4f} W".encode("ascii")

    def _measure_array(self, _rest: str, _is_query: bool) -> bytes:
        m = self.measured
        return f"{m.voltage:.4f} V, {m.current:.4f} A, {m.power:.4f} W".encode("ascii")

    # -- general queries ---------------------------------------------------------

    def _nominal_voltage(self, _rest: str, _is_query: bool) -> bytes:
        return f"{_NOMINAL_VOLTAGE:.4f} V".encode("ascii")

    def _nominal_current(self, _rest: str, _is_query: bool) -> bytes:
        return f"{_NOMINAL_CURRENT:.4f} A".encode("ascii")

    def _nominal_power(self, _rest: str, _is_query: bool) -> bytes:
        return f"{_NOMINAL_POWER:.4f} W".encode("ascii")

    def _device_class(self, _rest: str, _is_query: bool) -> bytes:
        return _DEVICE_CLASS.encode("ascii")

    # -- alarm counters ------------------------------------------------------------

    def _alarm_count_ovoltage(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.alarm_counters.overvoltage).encode("ascii")

    def _alarm_count_otemperature(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.alarm_counters.overtemperature).encode("ascii")

    def _alarm_count_opower(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.alarm_counters.overpower).encode("ascii")

    def _alarm_count_ocurrent(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.alarm_counters.overcurrent).encode("ascii")

    def _alarm_count_pfail(self, _rest: str, _is_query: bool) -> bytes:
        return str(self.alarm_counters.power_fail).encode("ascii")

    # -- device configuration -----------------------------------------------------

    def _power_stage_after_remote(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.config.power_stage_after_remote.encode("ascii")
        if not self._require_remote():
            return b""
        self.config.power_stage_after_remote = rest.strip().upper()
        return b""

    def _config_output_restore(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.config.output_restore.encode("ascii")
        if not self._require_remote():
            return b""
        self.config.output_restore = rest.strip().upper()
        return b""

    def _config_user_text(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.config.user_text}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.config.user_text = rest.strip().strip('"')
        return b""

    def _communicate_timeout(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.config.communication_timeout_ms).encode("ascii")
        if not self._require_remote():
            return b""
        self.config.communication_timeout_ms = int(rest)
        return b""

    def _alarm_action_pfail(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.config.alarm_action_pfail.encode("ascii")
        if not self._require_remote():
            return b""
        self.config.alarm_action_pfail = rest.strip().upper()
        return b""

    def _alarm_action_otemperature(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.config.alarm_action_otemperature.encode("ascii")
        if not self._require_remote():
            return b""
        self.config.alarm_action_otemperature = rest.strip().upper()
        return b""

    # -- LAN configuration (Gate 3) -------------------------------------------------

    def _lan_dhcp(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.lan.dhcp.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.dhcp = rest.strip().upper()
        return b""

    def _lan_address(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.address}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.address = rest.strip().strip('"')
        return b""

    def _lan_smask(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.subnet_mask}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.subnet_mask = rest.strip().strip('"')
        return b""

    def _lan_gateway(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.gateway}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.gateway = rest.strip().strip('"')
        return b""

    def _lan_hostname(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.hostname}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.hostname = rest.strip().strip('"')
        return b""

    def _lan_domain(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.domain}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.domain = rest.strip().strip('"')
        return b""

    def _lan_dns1(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.dns1}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.dns1 = rest.strip().strip('"')
        return b""

    def _lan_dns2(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return f'"{self.lan.dns2}"'.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.dns2 = rest.strip().strip('"')
        return b""

    def _lan_control(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.lan.control_port).encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.control_port = int(rest)
        return b""

    def _lan_keepalive(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.lan.keepalive.encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.keepalive = rest.strip().upper()
        return b""

    def _lan_timeout(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.lan.timeout_s).encode("ascii")
        if not self._require_remote():
            return b""
        self.lan.timeout_s = int(rest)
        return b""

    def _lan_mac(self, _rest: str, _is_query: bool) -> bytes:
        return self.lan.mac.encode("ascii")

    # -- analog interface configuration (Gate 3) -------------------------------------

    def _analog_reference(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return str(self.analog.reference_v).encode("ascii")
        if not self._require_remote():
            return b""
        self.analog.reference_v = int(float(rest))
        return b""

    def _analog_remsb_level(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.analog.remsb_level.encode("ascii")
        if not self._require_remote():
            return b""
        self.analog.remsb_level = rest.strip().upper()
        return b""

    def _analog_remsb_action(self, rest: str, is_query: bool) -> bytes:
        if is_query:
            return self.analog.remsb_action.encode("ascii")
        if not self._require_remote():
            return b""
        self.analog.remsb_action = rest.strip().upper()
        return b""

    # -- system/error --------------------------------------------------------------

    def _system_error(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b'0,"No error"'
        code, message = self._events.pop(0)
        return f'{code},"{message}"'.encode("ascii")

    def _system_error_all(self, _rest: str, _is_query: bool) -> bytes:
        if not self._events:
            return b'0,"No error"'
        parts = [f'{code},"{message}"' for code, message in self._events[:5]]
        self._events = self._events[len(parts):]
        return ", ".join(parts).encode("ascii")

    # -- routing table --------------------------------------------------------

    _ROUTES: ClassVar[dict[str, Callable]]


_ROUTES: dict[str, Callable] = {
    "*IDN": SimEaPs9000TInstrument._idn,
    "*CLS": SimEaPs9000TInstrument._cls,
    "*RST": SimEaPs9000TInstrument._rst,
    "*STB": SimEaPs9000TInstrument._stb,
    "*OPC": SimEaPs9000TInstrument._opc,
    "SYSTEM:LOCK": SimEaPs9000TInstrument._system_lock,
    "SYSTEM:LOCK:OWNER": SimEaPs9000TInstrument._system_lock_owner,
    "OUTPUT": SimEaPs9000TInstrument._output,
    "VOLTAGE": SimEaPs9000TInstrument._voltage,
    "CURRENT": SimEaPs9000TInstrument._current,
    "POWER": SimEaPs9000TInstrument._power,
    "VOLTAGE:PROTECTION": SimEaPs9000TInstrument._voltage_protection,
    "CURRENT:PROTECTION": SimEaPs9000TInstrument._current_protection,
    "POWER:PROTECTION": SimEaPs9000TInstrument._power_protection,
    "VOLTAGE:LIMIT:LOW": SimEaPs9000TInstrument._voltage_limit_low,
    "VOLTAGE:LIMIT:HIGH": SimEaPs9000TInstrument._voltage_limit_high,
    "CURRENT:LIMIT:LOW": SimEaPs9000TInstrument._current_limit_low,
    "CURRENT:LIMIT:HIGH": SimEaPs9000TInstrument._current_limit_high,
    "POWER:LIMIT:HIGH": SimEaPs9000TInstrument._power_limit_high,
    "MEASURE:VOLTAGE": SimEaPs9000TInstrument._measure_voltage,
    "MEASURE:CURRENT": SimEaPs9000TInstrument._measure_current,
    "MEASURE:POWER": SimEaPs9000TInstrument._measure_power,
    "MEASURE:ARRAY": SimEaPs9000TInstrument._measure_array,
    "SYSTEM:NOMINAL:VOLTAGE": SimEaPs9000TInstrument._nominal_voltage,
    "SYSTEM:NOMINAL:CURRENT": SimEaPs9000TInstrument._nominal_current,
    "SYSTEM:NOMINAL:POWER": SimEaPs9000TInstrument._nominal_power,
    "SYSTEM:DEVICE:CLASS": SimEaPs9000TInstrument._device_class,
    "SYSTEM:ALARM:COUNT:OVOLTAGE": SimEaPs9000TInstrument._alarm_count_ovoltage,
    "SYSTEM:ALARM:COUNT:OTEMPERATURE": SimEaPs9000TInstrument._alarm_count_otemperature,
    "SYSTEM:ALARM:COUNT:OPOWER": SimEaPs9000TInstrument._alarm_count_opower,
    "SYSTEM:ALARM:COUNT:OCURRENT": SimEaPs9000TInstrument._alarm_count_ocurrent,
    "SYSTEM:ALARM:COUNT:PFAIL": SimEaPs9000TInstrument._alarm_count_pfail,
    "POWER:STAGE:AFTER:REMOTE": SimEaPs9000TInstrument._power_stage_after_remote,
    "SYSTEM:CONFIG:OUTPUT:RESTORE": SimEaPs9000TInstrument._config_output_restore,
    "SYSTEM:CONFIG:USER:TEXT": SimEaPs9000TInstrument._config_user_text,
    "SYSTEM:COMMUNICATE:TIMEOUT": SimEaPs9000TInstrument._communicate_timeout,
    "SYSTEM:ALARM:ACTION:PFAIL": SimEaPs9000TInstrument._alarm_action_pfail,
    "SYSTEM:ALARM:ACTION:OTEMPERATURE": SimEaPs9000TInstrument._alarm_action_otemperature,
    "SYSTEM:ERROR": SimEaPs9000TInstrument._system_error,
    "SYSTEM:ERROR:ALL": SimEaPs9000TInstrument._system_error_all,
    "SYSTEM:COMMUNICATE:LAN:DHCP": SimEaPs9000TInstrument._lan_dhcp,
    "SYSTEM:COMMUNICATE:LAN:ADDRESS": SimEaPs9000TInstrument._lan_address,
    "SYSTEM:COMMUNICATE:LAN:SMASK": SimEaPs9000TInstrument._lan_smask,
    "SYSTEM:COMMUNICATE:LAN:GATEWAY": SimEaPs9000TInstrument._lan_gateway,
    "SYSTEM:COMMUNICATE:LAN:HOSTNAME": SimEaPs9000TInstrument._lan_hostname,
    "SYSTEM:COMMUNICATE:LAN:DOMAIN": SimEaPs9000TInstrument._lan_domain,
    "SYSTEM:COMMUNICATE:LAN:DNS1": SimEaPs9000TInstrument._lan_dns1,
    "SYSTEM:COMMUNICATE:LAN:DNS2": SimEaPs9000TInstrument._lan_dns2,
    "SYSTEM:COMMUNICATE:LAN:CONTROL": SimEaPs9000TInstrument._lan_control,
    "SYSTEM:COMMUNICATE:LAN:KEEPALIVE": SimEaPs9000TInstrument._lan_keepalive,
    "SYSTEM:COMMUNICATE:LAN:TIMEOUT": SimEaPs9000TInstrument._lan_timeout,
    "SYSTEM:COMMUNICATE:LAN:MAC": SimEaPs9000TInstrument._lan_mac,
    "SYSTEM:CONFIG:ANALOG:REFERENCE": SimEaPs9000TInstrument._analog_reference,
    "SYSTEM:CONFIG:ANALOG:REMSB:LEVEL": SimEaPs9000TInstrument._analog_remsb_level,
    "SYSTEM:CONFIG:ANALOG:REMSB:ACTION": SimEaPs9000TInstrument._analog_remsb_action,
}

SimEaPs9000TInstrument._ROUTES = _ROUTES
