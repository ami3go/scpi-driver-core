"""Robot Framework adapter for :mod:`keysight_n6700`.

The adapter intentionally keeps SCPI and hardware behavior in the underlying typed
Python driver.  This module provides Robot-friendly names, argument conversion,
named sessions, assertions, wait helpers, serializable return values, and safe
suite cleanup.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast

from robot.api import logger
from robot.api.deco import keyword, library, not_keyword

from keysight_n6700 import N6700

from .version import __version__

_NUMBER_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*"
    r"([pnumkMGTµμ]?)\s*(?:V|A|W|OHM|Ω|S)?\s*$",
    re.IGNORECASE,
)
_TIME_RE = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(ms|s|sec|secs|second|seconds|min|minute|minutes)?\s*$",
    re.IGNORECASE,
)
_PREFIX = {
    "": 1.0,
    "p": 1e-12,
    "n": 1e-9,
    "u": 1e-6,
    "µ": 1e-6,
    "μ": 1e-6,
    "m": 1e-3,
    "k": 1e3,
    "K": 1e3,
    "M": 1e6,
    "g": 1e9,
    "G": 1e9,
    "t": 1e12,
    "T": 1e12,
}
_TRUE = {"1", "true", "yes", "on", "enable", "enabled"}
_FALSE = {"0", "false", "no", "off", "disable", "disabled", "none", ""}


@not_keyword
def _as_bool(value: Any, *, name: str = "value") -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(f"{name} must be a boolean value, got {value!r}")


@not_keyword
def _as_float(value: Any, *, name: str = "value") -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, got boolean {value!r}")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip().replace(" ", "")
        match = _NUMBER_RE.match(text)
        if not match:
            raise ValueError(
                f"{name} must be numeric; engineering forms such as 5V, 250mA and 2.2k are supported, got {value!r}"
            )
        number, prefix = match.groups()
        # re.IGNORECASE would otherwise turn milli 'm' into mega. Preserve the source character.
        source_prefix = text[len(number) : len(number) + 1]
        multiplier = _PREFIX.get(source_prefix, _PREFIX.get(prefix, 1.0))
        result = float(number) * multiplier
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return result


@not_keyword
def _as_seconds(value: Any, *, name: str = "timeout") -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        result = float(value)
    else:
        match = _TIME_RE.match(str(value))
        if not match:
            raise ValueError(f"{name} must be seconds or a value such as 500ms, 5s, or 2min")
        number, unit = match.groups()
        result = float(number)
        unit = (unit or "s").lower()
        if unit == "ms":
            result /= 1000.0
        elif unit.startswith("min"):
            result *= 60.0
    if result < 0 or not math.isfinite(result):
        raise ValueError(f"{name} must be a finite non-negative duration")
    return result


@not_keyword
def _as_channel(value: Any) -> int:
    channel = int(value)
    if channel < 1 or channel > 4:
        raise ValueError(f"channel must be between 1 and 4, got {channel}")
    return channel


@not_keyword
def _as_channels(value: Any) -> list[int]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("channels cannot be empty")
        if text.lower() == "all":
            return [1, 2, 3, 4]
        raw = [part for part in re.split(r"[,;\s]+", text) if part]
    elif isinstance(value, Sequence):
        raw = list(value)
    else:
        raw = [value]
    channels = [_as_channel(item) for item in raw]
    if len(set(channels)) != len(channels):
        raise ValueError(f"channels contain duplicates: {channels}")
    return channels


@not_keyword
def _serialize(value: Any) -> Any:
    """Convert typed driver values into Robot-friendly Python primitives."""
    if is_dataclass(value):
        return {key: _serialize(item) for key, item in asdict(cast(Any, value)).items()}
    if isinstance(value, Mapping):
        return {(str(key) if isinstance(key, int) else key): _serialize(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    return value


@library(scope="SUITE", version=__version__, auto_keywords=False)
class KeysightN6700Library:
    """Robot Framework library for Keysight/Agilent N6700-series mainframes.

    ``auto_shutdown`` defaults to true. At disconnect and suite end, the library
    attempts ``shutdown_all()`` before closing each connection. Set it to false
    only when another safety controller owns the output state.

    ``strict_errors`` defaults to true. Mutating keywords drain the SCPI error
    queue after the command and fail the Robot keyword if the instrument reports
    an error.
    """

    ROBOT_LIBRARY_DOC_FORMAT = "ROBOT"
    ROBOT_LISTENER_API_VERSION = 2

    def __init__(self, auto_shutdown: Any = True, strict_errors: Any = True) -> None:
        self.auto_shutdown = _as_bool(auto_shutdown, name="auto_shutdown")
        self.strict_errors = _as_bool(strict_errors, name="strict_errors")
        self._sessions: dict[str, N6700] = {}
        self._current_alias: str | None = None
        self.ROBOT_LIBRARY_LISTENER = self

    # Robot listener hook. Leading underscore is required by listener API v2.
    def _end_suite(self, name: str, attrs: Mapping[str, Any]) -> None:  # noqa: ARG002
        self._close_all(raise_on_error=False)

    @not_keyword
    def _instrument(self, alias: str | None = None) -> N6700:
        selected = alias or self._current_alias
        if selected is None:
            raise RuntimeError("no N6700 connection is active; connect first")
        try:
            return self._sessions[selected]
        except KeyError as exc:
            raise RuntimeError(
                f"unknown N6700 alias {selected!r}; available aliases: {sorted(self._sessions)}"
            ) from exc

    @not_keyword
    def _post_write(self, instrument: N6700) -> None:
        if self.strict_errors:
            instrument.check_errors()

    @not_keyword
    def _register(self, alias: str, instrument: N6700, replace: Any = False) -> str:
        alias = str(alias).strip()
        if not alias:
            instrument.close()
            raise ValueError("alias cannot be empty")
        if alias in self._sessions:
            if not _as_bool(replace, name="replace"):
                instrument.close()
                raise ValueError(f"N6700 alias {alias!r} already exists")
            self._close_one(alias, raise_on_error=True)
        self._sessions[alias] = instrument
        self._current_alias = alias
        identity = instrument.idn()
        logger.info(
            f"Connected N6700 alias={alias!r}: {identity.manufacturer}, {identity.model}, serial={identity.serial}, firmware={identity.firmware}"
        )
        return alias

    @not_keyword
    def _close_one(self, alias: str, *, raise_on_error: bool) -> None:
        instrument = self._sessions.get(alias)
        if instrument is None:
            if raise_on_error:
                raise RuntimeError(f"unknown N6700 alias {alias!r}")
            return
        problems: list[str] = []
        if self.auto_shutdown:
            try:
                result = instrument.shutdown_all()
                if not result.success:
                    problems.append(f"shutdown incomplete: {_serialize(result)}")
            except Exception as exc:  # best-effort safety cleanup
                problems.append(f"shutdown failed: {exc}")
        try:
            instrument.close()
        except Exception as exc:
            problems.append(f"close failed: {exc}")
        self._sessions.pop(alias, None)
        if self._current_alias == alias:
            self._current_alias = next(iter(self._sessions), None)
        if problems:
            message = f"problems while closing N6700 alias {alias!r}: " + "; ".join(problems)
            if raise_on_error:
                raise RuntimeError(message)
            logger.warn(message)

    @not_keyword
    def _close_all(self, *, raise_on_error: bool) -> None:
        errors: list[str] = []
        for alias in list(self._sessions):
            try:
                self._close_one(alias, raise_on_error=True)
            except Exception as exc:
                errors.append(str(exc))
        if errors and raise_on_error:
            raise RuntimeError("; ".join(errors))

    @keyword("Connect To N6700")
    def connect_to_n6700(
        self,
        resource: str = "",
        alias: str = "default",
        connection_type: str = "visa",
        port: Any = 5025,
        discover: Any = True,
        reset_on_connect: Any = False,
        clear_errors_on_connect: Any = False,
        audit_log_path: str | None = None,
        replace: Any = False,
    ) -> str:
        """Connect using ``visa``, ``usb``, ``ethernet``/``socket``, or ``simulated``.

        For VISA and USB, ``resource`` is a VISA resource string. For Ethernet,
        ``resource`` is a hostname or IP address. The returned value is the alias.
        Connection is non-invasive unless ``reset_on_connect`` or
        ``clear_errors_on_connect`` is explicitly enabled.
        """
        kind = str(connection_type).strip().lower().replace("-", "_")
        options = {
            "discover": _as_bool(discover, name="discover"),
            "reset_on_connect": _as_bool(reset_on_connect, name="reset_on_connect"),
            "clear_errors_on_connect": _as_bool(
                clear_errors_on_connect, name="clear_errors_on_connect"
            ),
            "audit_log_path": Path(audit_log_path) if audit_log_path else None,
        }
        if kind in {"sim", "simulation", "simulated"}:
            instrument = N6700.connect_simulated(**options)
        elif kind in {"ethernet", "socket", "tcp", "tcpip"}:
            if not str(resource).strip():
                raise ValueError("resource must contain an Ethernet host or IP address")
            instrument = N6700.connect_ethernet(str(resource).strip(), int(port), **options)
        elif kind in {"visa", "usb"}:
            if not str(resource).strip():
                raise ValueError("resource must contain a VISA resource string")
            instrument = N6700.connect_visa(str(resource).strip(), **options)
        else:
            raise ValueError(
                "connection_type must be visa, usb, ethernet/socket, or simulated"
            )
        return self._register(str(alias), instrument, replace)

    @keyword("Connect To Simulated N6700")
    def connect_to_simulated_n6700(self, alias: str = "default", replace: Any = False) -> str:
        """Connect to the bundled four-channel simulator."""
        return self._register(alias, N6700.connect_simulated(), replace)

    @keyword("Connect To N6700 Via VISA")
    def connect_to_n6700_via_visa(
        self, resource: str, alias: str = "default", replace: Any = False
    ) -> str:
        """Connect to a VISA/USB/LAN VISA resource."""
        return self.connect_to_n6700(resource, alias, "visa", replace=replace)

    @keyword("Connect To N6700 Via USB")
    def connect_to_n6700_via_usb(
        self,
        resource: str,
        alias: str = "default",
        discover: Any = True,
        reset_on_connect: Any = False,
        clear_errors_on_connect: Any = False,
        audit_log_path: str | None = None,
        replace: Any = False,
    ) -> str:
        """Connect to an N6700 mainframe through a USBTMC VISA resource.

        Example resource: ``USB0::0x0957::0x0907::MY43014421::INSTR``.
        The connection remains non-invasive unless reset or error clearing is
        explicitly enabled.
        """
        return self.connect_to_n6700(
            resource=resource,
            alias=alias,
            connection_type="usb",
            discover=discover,
            reset_on_connect=reset_on_connect,
            clear_errors_on_connect=clear_errors_on_connect,
            audit_log_path=audit_log_path,
            replace=replace,
        )

    @keyword("Connect To N6700 Via Ethernet")
    def connect_to_n6700_via_ethernet(
        self, host: str, port: Any = 5025, alias: str = "default", replace: Any = False
    ) -> str:
        """Connect using a raw TCP socket, normally port 5025."""
        return self.connect_to_n6700(host, alias, "ethernet", port, replace=replace)

    @keyword("Select N6700")
    def select_n6700(self, alias: str) -> str:
        """Select the named connection used by following keywords."""
        self._instrument(alias)
        self._current_alias = alias
        return alias

    @keyword("Get Current N6700 Alias")
    def get_current_n6700_alias(self) -> str | None:
        """Return the current connection alias, or ``None``."""
        return self._current_alias

    @keyword("Get Connected N6700 Aliases")
    def get_connected_n6700_aliases(self) -> list[str]:
        """Return all open aliases."""
        return list(self._sessions)

    # ------------------------------------------------------------------
    # RFDS-002 mandatory universal keywords
    #
    # Thin, idempotent wrappers over the device-specific keywords above, kept
    # for generic/cross-driver tooling that expects the RFDS canonical names.
    # The device-specific keywords remain the primary, documented API.
    # ------------------------------------------------------------------
    @staticmethod
    @not_keyword
    def _resource_of(instrument: N6700) -> str:
        transport = instrument.transport
        if hasattr(transport, "resource"):
            return str(transport.resource)
        if hasattr(transport, "host"):
            return f"{transport.host}:{getattr(transport, 'port', '')}"
        return "simulated"

    @not_keyword
    def _connection_state(self, alias: str, instrument: N6700) -> dict[str, Any]:
        """Build the RFDS-002 Section 12.1 normalized connection-state dictionary."""
        identity_str: str | None = None
        try:
            identity = instrument.idn()
            identity_str = f"{identity.manufacturer},{identity.model},{identity.serial},{identity.firmware}"
        except Exception:
            identity_str = None
        return {
            "alias": alias,
            "resource": self._resource_of(instrument),
            "connected": True,
            "communication_ok": identity_str is not None,
            "transport": type(instrument.transport).__name__,
            "identity": identity_str,
            "timeout_s": None,
            "state": "connected",
        }

    @keyword("Connect")
    def connect(
        self,
        resource: str = "",
        alias: str = "default",
        timeout_s: float | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """RFDS-002 generic connect. ``resource`` is a VISA/USB resource string, host, or empty for simulated.

        Idempotent when ``alias`` is already connected to the same ``resource``.
        ``timeout_s`` is accepted for interface compatibility; this driver has no
        per-connection timeout setting to apply it to.
        """
        del timeout_s
        selected_alias = str(alias).strip() or "default"
        if selected_alias in self._sessions:
            instrument = self._sessions[selected_alias]
            existing_resource = self._resource_of(instrument)
            if resource and str(existing_resource) != str(resource):
                raise RuntimeError(
                    f"N6700 alias {selected_alias!r} is already connected to {existing_resource!r}; "
                    f"disconnect it before connecting it to {resource!r}."
                )
            return self._connection_state(selected_alias, instrument)
        connect_kwargs: dict[str, Any] = dict(options)
        connect_kwargs.setdefault("connection_type", "simulated" if not resource else "visa")
        self.connect_to_n6700(resource=resource, alias=selected_alias, **connect_kwargs)
        return self._connection_state(selected_alias, self._sessions[selected_alias])

    @keyword("Disconnect")
    def disconnect(self, alias: str | None = None) -> None:
        """RFDS-002 generic disconnect. Idempotent: succeeds even if already disconnected."""
        selected = alias or self._current_alias
        if selected is None or selected not in self._sessions:
            return
        self._close_one(selected, raise_on_error=True)

    @keyword("Is Connected")
    def is_connected(self, alias: str | None = None) -> bool:
        """Return whether ``alias`` (or the current session) is connected."""
        selected = alias or self._current_alias
        return selected is not None and selected in self._sessions

    @keyword("Get Connection State")
    def get_connection_state(self, alias: str | None = None, refresh: bool = False) -> dict[str, Any]:
        """Return the RFDS-002 Section 12.1 normalized connection-state dictionary."""
        selected = alias or self._current_alias
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
        instrument = self._sessions[selected]
        if _as_bool(refresh, name="refresh"):
            try:
                instrument.check_errors()
            except Exception:
                pass
        return self._connection_state(selected, instrument)

    @keyword("Check Communication")
    def check_communication(self, alias: str | None = None) -> bool:
        """Perform a bounded, non-destructive communication check. Raises on failure."""
        self._instrument(alias).idn()
        return True

    @keyword("Get Identity")
    def get_identity_generic(self, alias: str | None = None, refresh: bool = True) -> str:
        """Return a stable human-readable identity string."""
        del refresh
        identity = self._instrument(alias).idn()
        return f"{identity.manufacturer},{identity.model},{identity.serial},{identity.firmware}"

    @keyword("Disconnect N6700")
    def disconnect_n6700(self, alias: str | None = None) -> None:
        """Safely disconnect one connection."""
        selected = alias or self._current_alias
        if selected is None:
            raise RuntimeError("no N6700 connection is active")
        self._close_one(selected, raise_on_error=True)

    @keyword("Disconnect All N6700")
    def disconnect_all_n6700(self) -> None:
        """Safely disconnect every connection."""
        self._close_all(raise_on_error=True)

    @keyword("Get N6700 Identity")
    def get_n6700_identity(self, alias: str | None = None) -> dict[str, Any]:
        """Return manufacturer, model, serial and firmware as a dictionary."""
        return _serialize(self._instrument(alias).idn())

    @keyword("Get N6700 Channel Count")
    def get_n6700_channel_count(self, alias: str | None = None) -> int:
        """Return the installed channel count."""
        return self._instrument(alias).channel_count()

    @keyword("Discover N6700 Modules")
    def discover_n6700_modules(self, alias: str | None = None) -> dict[str, Any]:
        """Discover modules and return capability dictionaries keyed by channel."""
        return _serialize(self._instrument(alias).discover_modules())

    @keyword("Get N6700 Channel Information")
    def get_n6700_channel_information(
        self, channel: Any, alias: str | None = None
    ) -> dict[str, Any]:
        """Return model, serial, options and capabilities for one channel."""
        ch = _as_channel(channel)
        instrument = self._instrument(alias)
        capabilities = instrument.channel(ch).capabilities
        return {
            "channel": ch,
            "model": instrument.channel_model(ch),
            "serial": instrument.channel_serial(ch),
            "options": instrument.channel_options(ch),
            "capabilities": _serialize(capabilities),
        }

    @keyword("Write N6700 SCPI")
    def write_n6700_scpi(
        self, command: str, check_errors: Any | None = None, alias: str | None = None
    ) -> None:
        """Write a raw SCPI command.

        Prefer typed keywords for normal tests. Raw SCPI bypasses capability checks.
        """
        instrument = self._instrument(alias)
        instrument.write_scpi(str(command))
        if self.strict_errors if check_errors is None else _as_bool(check_errors):
            instrument.check_errors()

    @keyword("Query N6700 SCPI")
    def query_n6700_scpi(self, command: str, alias: str | None = None) -> str:
        """Send a raw SCPI query and return its response string."""
        return self._instrument(alias).query_scpi(str(command))

    @keyword("Clear N6700 Status")
    def clear_n6700_status(self, alias: str | None = None) -> None:
        """Send ``*CLS``."""
        self._instrument(alias).clear_status()

    @keyword("Reset N6700")
    def reset_n6700(self, alias: str | None = None) -> None:
        """Reset the instrument. This can change output configuration."""
        instrument = self._instrument(alias)
        instrument.reset()
        self._post_write(instrument)

    @keyword("Run N6700 Self Test")
    def run_n6700_self_test(self, alias: str | None = None) -> dict[str, Any]:
        """Run ``*TST?`` and return ``code``, ``message`` and ``passed``."""
        result = self._instrument(alias).self_test()
        data = _serialize(result)
        data["passed"] = result.passed
        return data

    @keyword("Check N6700 Errors")
    def check_n6700_errors(self, alias: str | None = None) -> None:
        """Fail if the instrument SCPI error queue is not empty."""
        self._instrument(alias).check_errors()

    @keyword("Drain N6700 Errors")
    def drain_n6700_errors(self, alias: str | None = None) -> list[dict[str, Any]]:
        """Drain and return all SCPI errors without failing."""
        return _serialize(self._instrument(alias).drain_errors())

    @keyword("Set N6700 Voltage")
    def set_n6700_voltage(
        self, channel: Any, voltage: Any, voltage_range: Any | None = None, alias: str | None = None
    ) -> float:
        """Set a power-supply/SMU voltage setpoint and return volts."""
        instrument = self._instrument(alias)
        value = _as_float(voltage, name="voltage")
        range_value = None if voltage_range is None or str(voltage_range).strip() == "" else voltage_range
        if range_value is not None and str(range_value).upper() not in {"MIN", "MAX", "DEF"}:
            range_value = _as_float(range_value, name="voltage_range")
        instrument.power_supply(_as_channel(channel)).set_voltage_setpoint(
            value, voltage_range=range_value
        )
        self._post_write(instrument)
        return value

    @keyword("Get N6700 Voltage Setpoint")
    def get_n6700_voltage_setpoint(self, channel: Any, alias: str | None = None) -> float:
        """Return the programmed voltage setpoint."""
        return self._instrument(alias).power_supply(_as_channel(channel)).get_voltage_setpoint()

    @keyword("Set N6700 Current Limit")
    def set_n6700_current_limit(
        self, channel: Any, current: Any, current_range: Any | None = None, alias: str | None = None
    ) -> float:
        """Set a power-supply/SMU current limit and return amperes."""
        instrument = self._instrument(alias)
        value = _as_float(current, name="current")
        range_value = None if current_range is None or str(current_range).strip() == "" else current_range
        if range_value is not None and str(range_value).upper() not in {"MIN", "MAX", "DEF"}:
            range_value = _as_float(range_value, name="current_range")
        instrument.power_supply(_as_channel(channel)).set_current_limit(
            value, current_range=range_value
        )
        self._post_write(instrument)
        return value

    @keyword("Get N6700 Current Limit")
    def get_n6700_current_limit(self, channel: Any, alias: str | None = None) -> float:
        """Return the programmed current limit."""
        return self._instrument(alias).power_supply(_as_channel(channel)).get_current_limit()

    @keyword("Configure N6700 Power Supply Channel")
    def configure_n6700_power_supply_channel(
        self,
        channel: Any,
        voltage: Any,
        current_limit: Any,
        output: Any = False,
        ovp: Any | None = None,
        ocp: Any | None = None,
        alias: str | None = None,
    ) -> dict[str, Any]:
        """Configure voltage/current/protection and optionally enable output.

        Output remains off by default. Values accept engineering notation such as
        ``12V`` and ``500mA``.
        """
        instrument = self._instrument(alias)
        ch_num = _as_channel(channel)
        ch = instrument.power_supply(ch_num)
        voltage_v = _as_float(voltage, name="voltage")
        current_a = _as_float(current_limit, name="current_limit")
        ch.set_voltage_setpoint(voltage_v)
        ch.set_current_limit(current_a)
        ovp_v = None
        if ovp is not None and str(ovp).strip() != "":
            ovp_v = _as_float(ovp, name="ovp")
            ch.set_ovp(ovp_v)
        ocp_enabled = None
        if ocp is not None and str(ocp).strip() != "":
            ocp_enabled = _as_bool(ocp, name="ocp")
            ch.set_ocp(ocp_enabled)
        output_enabled = _as_bool(output, name="output")
        ch.set_output(output_enabled)
        self._post_write(instrument)
        return {
            "channel": ch_num,
            "voltage_V": voltage_v,
            "current_limit_A": current_a,
            "ovp_V": ovp_v,
            "ocp_enabled": ocp_enabled,
            "output_enabled": output_enabled,
        }

    @keyword("Set N6700 Output")
    def set_n6700_output(
        self, channel: Any, enabled: Any, alias: str | None = None
    ) -> bool:
        """Enable or disable one power-supply/SMU output."""
        instrument = self._instrument(alias)
        state = _as_bool(enabled, name="enabled")
        instrument.power_supply(_as_channel(channel)).set_output(state)
        self._post_write(instrument)
        return state

    @keyword("Turn On N6700 Output")
    def turn_on_n6700_output(self, channel: Any, alias: str | None = None) -> None:
        """Enable one power-supply/SMU output."""
        self.set_n6700_output(channel, True, alias)

    @keyword("Turn Off N6700 Output")
    def turn_off_n6700_output(self, channel: Any, alias: str | None = None) -> None:
        """Disable one power-supply/SMU output."""
        self.set_n6700_output(channel, False, alias)

    @keyword("Get N6700 Output State")
    def get_n6700_output_state(self, channel: Any, alias: str | None = None) -> bool:
        """Return one power-supply/SMU output state."""
        return self._instrument(alias).power_supply(_as_channel(channel)).get_output()

    @keyword("Set N6700 Outputs")
    def set_n6700_outputs(
        self, channels: Any, enabled: Any, alias: str | None = None
    ) -> list[int]:
        """Set several power-supply/SMU outputs; ``channels`` may be ``1,2,4``."""
        instrument = self._instrument(alias)
        parsed = _as_channels(channels)
        instrument.set_power_outputs(parsed, _as_bool(enabled, name="enabled"))
        self._post_write(instrument)
        return parsed

    @keyword("Set N6700 Over Voltage Protection")
    def set_n6700_over_voltage_protection(
        self, channel: Any, voltage: Any, alias: str | None = None
    ) -> float:
        """Set OVP threshold in volts."""
        instrument = self._instrument(alias)
        value = _as_float(voltage, name="voltage")
        instrument.power_supply(_as_channel(channel)).set_ovp(value)
        self._post_write(instrument)
        return value

    @keyword("Get N6700 Over Voltage Protection")
    def get_n6700_over_voltage_protection(
        self, channel: Any, alias: str | None = None
    ) -> float:
        """Return OVP threshold in volts."""
        return self._instrument(alias).power_supply(_as_channel(channel)).get_ovp()

    @keyword("Set N6700 Over Current Protection")
    def set_n6700_over_current_protection(
        self, channel: Any, enabled: Any, alias: str | None = None
    ) -> bool:
        """Enable or disable OCP."""
        instrument = self._instrument(alias)
        state = _as_bool(enabled, name="enabled")
        instrument.power_supply(_as_channel(channel)).set_ocp(state)
        self._post_write(instrument)
        return state

    @keyword("Get N6700 Over Current Protection")
    def get_n6700_over_current_protection(
        self, channel: Any, alias: str | None = None
    ) -> bool:
        """Return OCP state."""
        return self._instrument(alias).power_supply(_as_channel(channel)).get_ocp()

    @keyword("Measure N6700 Voltage")
    def measure_n6700_voltage(self, channel: Any, alias: str | None = None) -> float:
        """Measure channel voltage in volts."""
        return self._instrument(alias).channel(_as_channel(channel)).measure_voltage()

    @keyword("Measure N6700 Current")
    def measure_n6700_current(self, channel: Any, alias: str | None = None) -> float:
        """Measure channel current in amperes."""
        return self._instrument(alias).channel(_as_channel(channel)).measure_current()

    @keyword("Measure N6700 Power")
    def measure_n6700_power(self, channel: Any, alias: str | None = None) -> dict[str, Any]:
        """Measure channel power and return value, source and timestamp."""
        return _serialize(self._instrument(alias).channel(_as_channel(channel)).measure_power())

    @keyword("Measure N6700 Channel")
    def measure_n6700_channel(self, channel: Any, alias: str | None = None) -> dict[str, Any]:
        """Return voltage, current, power, source and timestamp for one channel."""
        return _serialize(self._instrument(alias).channel(_as_channel(channel)).measure())

    @keyword("Measure All N6700 Channels")
    def measure_all_n6700_channels(self, alias: str | None = None) -> dict[str, Any]:
        """Return measurement dictionaries keyed by channel number."""
        return _serialize(self._instrument(alias).measure_all())

    @not_keyword
    def _assert_near(self, actual: float, expected: Any, tolerance: Any, quantity: str) -> None:
        target = _as_float(expected, name="expected")
        tol = _as_float(tolerance, name="tolerance")
        if tol < 0:
            raise ValueError("tolerance cannot be negative")
        error = abs(actual - target)
        if error > tol:
            raise AssertionError(
                f"{quantity} {actual:.12g} differs from expected {target:.12g} by {error:.12g}, exceeding tolerance {tol:.12g}"
            )

    @keyword("N6700 Voltage Should Be")
    def n6700_voltage_should_be(
        self, channel: Any, expected: Any, tolerance: Any = "0.1V", alias: str | None = None
    ) -> float:
        """Measure voltage and fail unless it is within absolute tolerance."""
        actual = self.measure_n6700_voltage(channel, alias)
        self._assert_near(actual, expected, tolerance, "Voltage")
        return actual

    @keyword("N6700 Current Should Be")
    def n6700_current_should_be(
        self, channel: Any, expected: Any, tolerance: Any = "10mA", alias: str | None = None
    ) -> float:
        """Measure current and fail unless it is within absolute tolerance."""
        actual = self.measure_n6700_current(channel, alias)
        self._assert_near(actual, expected, tolerance, "Current")
        return actual

    @keyword("N6700 Power Should Be")
    def n6700_power_should_be(
        self, channel: Any, expected: Any, tolerance: Any = "0.1W", alias: str | None = None
    ) -> float:
        """Measure power and fail unless it is within absolute tolerance."""
        result = self._instrument(alias).channel(_as_channel(channel)).measure_power()
        if result.power_W is None:
            raise AssertionError("Power measurement is unavailable")
        self._assert_near(result.power_W, expected, tolerance, "Power")
        return result.power_W

    @keyword("N6700 Output Should Be")
    def n6700_output_should_be(
        self, channel: Any, expected: Any, alias: str | None = None
    ) -> bool:
        """Fail unless output state matches the expected boolean."""
        actual = self.get_n6700_output_state(channel, alias)
        wanted = _as_bool(expected, name="expected")
        if actual != wanted:
            raise AssertionError(f"Output state was {actual}, expected {wanted}")
        return actual

    @keyword("Wait Until N6700 Voltage Is In Range")
    def wait_until_n6700_voltage_is_in_range(
        self,
        channel: Any,
        minimum: Any,
        maximum: Any,
        timeout: Any = "10s",
        poll_interval: Any = "200ms",
        alias: str | None = None,
    ) -> float:
        """Poll voltage until ``minimum <= value <= maximum`` or fail on timeout."""
        low = _as_float(minimum, name="minimum")
        high = _as_float(maximum, name="maximum")
        if low > high:
            raise ValueError("minimum cannot be greater than maximum")
        timeout_s = _as_seconds(timeout)
        poll_s = _as_seconds(poll_interval, name="poll_interval")
        deadline = time.monotonic() + timeout_s
        last = self.measure_n6700_voltage(channel, alias)
        while not low <= last <= high:
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"Voltage did not enter range [{low:.12g}, {high:.12g}] within {timeout_s:.3g}s; last value was {last:.12g}"
                )
            time.sleep(poll_s)
            last = self.measure_n6700_voltage(channel, alias)
        return last

    @keyword("Get N6700 Protection Status")
    def get_n6700_protection_status(
        self, channel: Any, alias: str | None = None
    ) -> dict[str, Any]:
        """Return protection status for one channel."""
        return _serialize(self._instrument(alias).channel(_as_channel(channel)).get_protection_status())

    @keyword("Clear N6700 Protection")
    def clear_n6700_protection(
        self,
        channel: Any,
        restore_output: Any = False,
        force_output_off_first: Any = True,
        verify_cleared: Any = True,
        alias: str | None = None,
    ) -> dict[str, Any]:
        """Safely clear channel protection and return before/after states.

        The safe default turns the output/input off first and does not restore it.
        """
        instrument = self._instrument(alias)
        result = instrument.clear_protection(
            _as_channel(channel),
            restore_output=_as_bool(restore_output, name="restore_output"),
            force_output_off_first=_as_bool(
                force_output_off_first, name="force_output_off_first"
            ),
            verify_cleared=_as_bool(verify_cleared, name="verify_cleared"),
        )
        return _serialize(result)

    @keyword("Shutdown All N6700 Channels")
    def shutdown_all_n6700_channels(self, alias: str | None = None) -> dict[str, Any]:
        """Attempt to disable every output/input and return per-channel results."""
        result = self._instrument(alias).shutdown_all()
        data = _serialize(result)
        data["success"] = result.success
        return data

    @keyword("Set N6700 SMU Mode")
    def set_n6700_smu_mode(
        self, channel: Any, mode: str, alias: str | None = None
    ) -> str:
        """Set an SMU channel to ``voltage`` or ``current`` priority."""
        selected = str(mode).strip().lower()
        if selected not in {"voltage", "current"}:
            raise ValueError("mode must be voltage or current")
        instrument = self._instrument(alias)
        instrument.smu(_as_channel(channel)).set_smu_mode(selected)  # type: ignore[arg-type]
        self._post_write(instrument)
        return selected

    @keyword("Get N6700 SMU Mode")
    def get_n6700_smu_mode(self, channel: Any, alias: str | None = None) -> str:
        """Return SMU priority mode."""
        return self._instrument(alias).smu(_as_channel(channel)).get_smu_mode()

    @keyword("Configure N6700 SMU Voltage Priority")
    def configure_n6700_smu_voltage_priority(
        self,
        channel: Any,
        voltage: Any,
        current_limit: Any,
        voltage_limit: Any | None = None,
        output: Any = False,
        alias: str | None = None,
    ) -> dict[str, Any]:
        """Configure an SMU in voltage-priority mode; output defaults off."""
        instrument = self._instrument(alias)
        ch_num = _as_channel(channel)
        voltage_v = _as_float(voltage, name="voltage")
        current_a = _as_float(current_limit, name="current_limit")
        limit_v = (
            None
            if voltage_limit is None or str(voltage_limit).strip() == ""
            else _as_float(voltage_limit, name="voltage_limit")
        )
        enabled = _as_bool(output, name="output")
        instrument.smu(ch_num).configure_voltage_priority(
            voltage_v, current_a, voltage_limit=limit_v, output=enabled, verify=self.strict_errors
        )
        return {
            "channel": ch_num,
            "mode": "voltage",
            "voltage_V": voltage_v,
            "current_limit_A": current_a,
            "voltage_limit_V": limit_v,
            "output_enabled": enabled,
        }

    @keyword("Configure N6700 SMU Current Priority")
    def configure_n6700_smu_current_priority(
        self,
        channel: Any,
        current: Any,
        voltage_limit: Any,
        output: Any = False,
        alias: str | None = None,
    ) -> dict[str, Any]:
        """Configure an SMU in current-priority mode; output defaults off."""
        instrument = self._instrument(alias)
        ch_num = _as_channel(channel)
        current_a = _as_float(current, name="current")
        limit_v = _as_float(voltage_limit, name="voltage_limit")
        enabled = _as_bool(output, name="output")
        instrument.smu(ch_num).configure_current_priority(
            current_a, limit_v, output=enabled, verify=self.strict_errors
        )
        return {
            "channel": ch_num,
            "mode": "current",
            "current_A": current_a,
            "voltage_limit_V": limit_v,
            "output_enabled": enabled,
        }

    @keyword("Set N6700 SMU Output Off Mode")
    def set_n6700_smu_output_off_mode(
        self, channel: Any, mode: str, alias: str | None = None
    ) -> str:
        """Set supported SMU output-off mode to ``high_z`` or ``low_z``."""
        selected = str(mode).strip().lower().replace("-", "_")
        if selected not in {"high_z", "low_z"}:
            raise ValueError("mode must be high_z or low_z")
        instrument = self._instrument(alias)
        instrument.smu(_as_channel(channel)).set_smu_output_off_mode(selected)  # type: ignore[arg-type]
        self._post_write(instrument)
        return selected

    @keyword("Get N6700 SMU Output Off Mode")
    def get_n6700_smu_output_off_mode(
        self, channel: Any, alias: str | None = None
    ) -> str:
        """Return supported SMU output-off mode."""
        return self._instrument(alias).smu(_as_channel(channel)).get_smu_output_off_mode()

    @keyword("Set N6700 Load Mode")
    def set_n6700_load_mode(
        self, channel: Any, mode: str, alias: str | None = None
    ) -> str:
        """Set load mode to ``cc``, ``cv``, ``cr`` or ``cp``."""
        selected = str(mode).strip().lower()
        if selected not in {"cc", "cv", "cr", "cp"}:
            raise ValueError("mode must be cc, cv, cr, or cp")
        instrument = self._instrument(alias)
        instrument.load(_as_channel(channel)).set_load_mode(selected)  # type: ignore[arg-type]
        self._post_write(instrument)
        return selected

    @keyword("Get N6700 Load Mode")
    def get_n6700_load_mode(self, channel: Any, alias: str | None = None) -> str:
        """Return electronic-load mode."""
        return self._instrument(alias).load(_as_channel(channel)).get_load_mode()

    @keyword("Set N6700 Load Level")
    def set_n6700_load_level(
        self, channel: Any, value: Any, mode: str | None = None, alias: str | None = None
    ) -> float:
        """Set the level for CC/CV/CR/CP mode.

        When ``mode`` is omitted, the current instrument mode is used.
        """
        instrument = self._instrument(alias)
        load = instrument.load(_as_channel(channel))
        selected = (mode or load.get_load_mode()).strip().lower()
        if selected not in {"cc", "cv", "cr", "cp"}:
            raise ValueError("mode must be cc, cv, cr, or cp")
        level = _as_float(value, name="value")
        load.set_load_mode(selected)  # type: ignore[arg-type]
        {
            "cc": load.set_load_current,
            "cv": load.set_load_voltage,
            "cr": load.set_load_resistance,
            "cp": load.set_load_power,
        }[selected](level)
        self._post_write(instrument)
        return level

    @keyword("Get N6700 Load Level")
    def get_n6700_load_level(
        self, channel: Any, mode: str | None = None, alias: str | None = None
    ) -> float:
        """Return load level for CC/CV/CR/CP mode."""
        load = self._instrument(alias).load(_as_channel(channel))
        selected = (mode or load.get_load_mode()).strip().lower()
        getters = {
            "cc": load.get_load_current,
            "cv": load.get_load_voltage,
            "cr": load.get_load_resistance,
            "cp": load.get_load_power,
        }
        try:
            return getters[selected]()
        except KeyError as exc:
            raise ValueError("mode must be cc, cv, cr, or cp") from exc

    @keyword("Set N6700 Load Input")
    def set_n6700_load_input(
        self, channel: Any, enabled: Any, alias: str | None = None
    ) -> bool:
        """Enable or disable an electronic-load input."""
        instrument = self._instrument(alias)
        state = _as_bool(enabled, name="enabled")
        instrument.load(_as_channel(channel)).set_input(state)
        self._post_write(instrument)
        return state

    @keyword("Turn On N6700 Load Input")
    def turn_on_n6700_load_input(self, channel: Any, alias: str | None = None) -> None:
        """Enable an electronic-load input."""
        self.set_n6700_load_input(channel, True, alias)

    @keyword("Turn Off N6700 Load Input")
    def turn_off_n6700_load_input(self, channel: Any, alias: str | None = None) -> None:
        """Disable an electronic-load input."""
        self.set_n6700_load_input(channel, False, alias)

    @keyword("Get N6700 Load Input State")
    def get_n6700_load_input_state(self, channel: Any, alias: str | None = None) -> bool:
        """Return electronic-load input state."""
        return self._instrument(alias).load(_as_channel(channel)).get_input()

    @keyword("Configure N6700 Load CC")
    def configure_n6700_load_cc(
        self, channel: Any, current: Any, input_on: Any = False, alias: str | None = None
    ) -> dict[str, Any]:
        """Configure constant-current load mode; input defaults off."""
        instrument = self._instrument(alias)
        ch_num = _as_channel(channel)
        current_a = _as_float(current, name="current")
        enabled = _as_bool(input_on, name="input_on")
        instrument.load(ch_num).configure_cc(
            current_a, input_on=enabled, verify=self.strict_errors
        )
        return {
            "channel": ch_num,
            "mode": "cc",
            "current_A": current_a,
            "input_enabled": enabled,
        }
