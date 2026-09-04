"""Typed core driver for the Keysight N6700 modular power-supply/SMU/electronic-load mainframe.

``N6700`` owns SCPI command construction, response parsing, module-capability
dispatch (a mainframe can hold any mix of power-supply, SMU, and electronic-load
modules — see ``capabilities.py``/``channel.py``), and connection lifecycle over
VISA, USB, a raw Ethernet socket, or the bundled simulator (``transport.py``).
The Robot Framework adapter (``KeysightN6700Library/library.py``) is a thin
layer on top of this module and must not duplicate SCPI/hardware logic.

``write_scpi``/``query_scpi`` below are the single transport-boundary choke
point every typed keyword and raw SCPI call routes through; when
``audit_log_path`` is set, every transaction passing through them is appended
to that file as a JSONL trace (see ``_append_protocol_trace`` and
``docs/audit_logging.md``) — this is this driver's per-session, opt-in
troubleshooting log, distinct from the RFDS-019 self-check's own evidence
bundle under ``tests/conformance/`` (see ``docs/n6775a_self_check.md``).
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .capabilities import ChannelCapabilities, classify_module
from .channel import BaseChannel, ElectronicLoadChannel, PowerSupplyChannel, SMUChannel
from .exceptions import InvalidChannelError, N6700CommandError, UnsupportedFeatureError
from .scpi import format_channel_list, parse_error, parse_idn
from .transport import PyVisaTransport, RawSocketTransport, SimulatedTransport, Transport
from .types import (
    AuditRecord,
    InstrumentIdentity,
    Measurement,
    OperationStatus,
    PowerMeasurement,
    ProtectionClearResult,
    QuestionableStatus,
    RemoteState,
    ScpiErrorRecord,
    SelfTestResult,
    ShutdownChannelResult,
    ShutdownResult,
)


class N6700:
    """Safe driver for an N6700-family modular power system.

    Connection is non-invasive by default: no reset, no output changes, no protection clear,
    no nonvolatile writes.
    """

    def __init__(
        self,
        transport: Transport,
        *,
        discover: bool = True,
        reset_on_connect: bool = False,
        clear_errors_on_connect: bool = False,
        command_lock: bool = True,
        audit_log_path: str | Path | None = None,
    ) -> None:
        self.transport = transport
        self._lock = threading.RLock() if command_lock else _NullLock()
        self._identity: InstrumentIdentity | None = None
        self._channel_count = 0
        self._capabilities: dict[int, ChannelCapabilities] = {}
        self._channels: dict[int, BaseChannel] = {}
        self.audit_log_path = Path(audit_log_path) if audit_log_path else None
        if reset_on_connect:
            self.reset()
        self._identity = parse_idn(self.query_scpi("*IDN?"))
        if clear_errors_on_connect:
            self.drain_errors()
        if discover:
            self.discover_modules()

    @classmethod
    def connect_usb(cls, resource: str, **options: Any) -> N6700:
        return cls(PyVisaTransport(resource), **options)

    @classmethod
    def connect_visa(cls, resource: str, **options: Any) -> N6700:
        return cls(PyVisaTransport(resource), **options)

    @classmethod
    def connect_ethernet(cls, host: str, port: int = 5025, **options: Any) -> N6700:
        return cls(RawSocketTransport(host, port), **options)

    @classmethod
    def connect_simulated(cls, simulator: object | None = None, **options: Any) -> N6700:
        if simulator is None:
            from .simulator import SimN6700Instrument

            simulator = SimN6700Instrument()
        return cls(SimulatedTransport(simulator), **options)

    def __enter__(self) -> N6700:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    @property
    def channels(self) -> Mapping[int, BaseChannel]:
        return self._channels

    def _append_protocol_trace(
        self,
        *,
        operation: str,
        command: str,
        response: str | None,
        started_unix: float,
        duration_s: float,
        error: str | None = None,
    ) -> None:
        """Append one transport-boundary SCPI event when audit logging is enabled."""
        if self.audit_log_path is None:
            return
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp_iso": datetime.fromtimestamp(
                started_unix, tz=timezone.utc
            ).isoformat(),
            "timestamp_unix": started_unix,
            "operation": operation,
            "command": command,
            "response": response,
            "error": error,
            "duration_s": duration_s,
        }
        with self.audit_log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, default=str) + "\n")

    def write_scpi(self, command: str) -> None:
        with self._lock:
            started_unix = time.time()
            started = time.perf_counter()
            try:
                self.transport.write(command)
            except Exception as exc:
                self._append_protocol_trace(
                    operation="write",
                    command=command,
                    response=None,
                    started_unix=started_unix,
                    duration_s=time.perf_counter() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            self._append_protocol_trace(
                operation="write",
                command=command,
                response=None,
                started_unix=started_unix,
                duration_s=time.perf_counter() - started,
            )

    def query_scpi(self, command: str) -> str:
        with self._lock:
            started_unix = time.time()
            started = time.perf_counter()
            try:
                response = self.transport.query(command)
            except Exception as exc:
                self._append_protocol_trace(
                    operation="query",
                    command=command,
                    response=None,
                    started_unix=started_unix,
                    duration_s=time.perf_counter() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            self._append_protocol_trace(
                operation="query",
                command=command,
                response=response,
                started_unix=started_unix,
                duration_s=time.perf_counter() - started,
            )
            return response

    def idn(self) -> InstrumentIdentity:
        if self._identity is None:
            self._identity = parse_idn(self.query_scpi("*IDN?"))
        return self._identity

    def reset(self) -> None:
        self.write_scpi("*RST")

    def clear_status(self) -> None:
        self.write_scpi("*CLS")

    def self_test(self) -> SelfTestResult:
        resp = self.query_scpi("*TST?")
        if "," in resp:
            code_s, msg = resp.split(",", 1)
            return SelfTestResult(int(code_s), msg.strip().strip('"'))
        return SelfTestResult(int(resp), "")

    def get_error(self) -> ScpiErrorRecord:
        return parse_error(self.query_scpi("SYST:ERR?"))

    def drain_errors(self) -> list[ScpiErrorRecord]:
        errors: list[ScpiErrorRecord] = []
        for _ in range(32):
            err = self.get_error()
            if err.is_ok:
                break
            errors.append(err)
        return errors

    def check_errors(self) -> None:
        errors = self.drain_errors()
        if errors:
            raise N6700CommandError("instrument reported SCPI errors", errors)

    def operation_complete(self, timeout: float | None = None) -> bool:
        del timeout
        return self.query_scpi("*OPC?").strip() == "1"

    def wait(self) -> None:
        self.write_scpi("*WAI")

    def status_byte(self) -> int:
        return int(self.query_scpi("*STB?"))

    def standard_event_status(self) -> int:
        return int(self.query_scpi("*ESR?"))

    def get_remote_state(self) -> RemoteState:
        if isinstance(self.transport, SimulatedTransport):
            value = self.query_scpi("SYST:REM?").strip().lower()
            if value in {"local", "remote", "remote_lockout"}:
                return value  # type: ignore[return-value]
        raise UnsupportedFeatureError("remote/local query is not supported by this transport")

    def set_remote_state(self, state: RemoteState) -> None:
        if not isinstance(self.transport, SimulatedTransport):
            raise UnsupportedFeatureError("remote/local control is transport-specific and unsupported here")
        command = {"local": "SYST:LOC", "remote": "SYST:REM", "remote_lockout": "SYST:RWL"}[state]
        self.write_scpi(command)

    def remote_lockout(self, enabled: bool) -> None:
        self.set_remote_state("remote_lockout" if enabled else "remote")

    def channel_count(self) -> int:
        if self._channel_count == 0:
            self._channel_count = int(self.query_scpi("SYST:CHAN:COUN?"))
        return self._channel_count

    def _validate_channel(self, channel: int) -> None:
        count = self.channel_count()
        if channel < 1 or channel > count or channel > 4:
            raise InvalidChannelError(f"invalid channel {channel}; installed count is {count}")

    def channel_model(self, channel: int) -> str:
        self._validate_channel(channel)
        return self.query_scpi(f"SYST:CHAN:MOD? {format_channel_list(channel)}").strip().strip('"')

    def channel_options(self, channel: int) -> list[str]:
        self._validate_channel(channel)
        resp = self.query_scpi(f"SYST:CHAN:OPT? {format_channel_list(channel)}")
        normalized = resp.strip().strip('"')
        if normalized in {"", "0", "+0"}:
            return []
        return [item.strip().strip('"') for item in resp.split(",") if item.strip().strip('"')]

    def channel_serial(self, channel: int) -> str:
        self._validate_channel(channel)
        return self.query_scpi(f"SYST:CHAN:SER? {format_channel_list(channel)}").strip().strip('"')

    def discover_modules(self) -> dict[int, ChannelCapabilities]:
        count = self.channel_count()
        self._capabilities.clear()
        self._channels.clear()
        for ch in range(1, count + 1):
            model = self.channel_model(ch)
            options = self.channel_options(ch)
            caps = classify_module(model, options)
            self._capabilities[ch] = caps
            if caps.module_type == "smu":
                self._channels[ch] = SMUChannel(self, ch, caps)
            elif caps.module_type == "power_supply":
                self._channels[ch] = PowerSupplyChannel(self, ch, caps)
            elif caps.module_type == "electronic_load":
                self._channels[ch] = ElectronicLoadChannel(self, ch, caps)
            else:
                self._channels[ch] = BaseChannel(self, ch, caps)
        return dict(self._capabilities)

    def channel(self, channel: int) -> BaseChannel:
        self._validate_channel(channel)
        if channel not in self._channels:
            self.discover_modules()
        return self._channels[channel]

    def get_channel(self, channel: int) -> BaseChannel:
        return self.channel(channel)

    def power_supply(self, channel: int) -> PowerSupplyChannel:
        ch = self.channel(channel)
        if not isinstance(ch, PowerSupplyChannel) or isinstance(ch, ElectronicLoadChannel):
            raise UnsupportedFeatureError(f"channel {channel} is not a power-supply/SMU output")
        return ch

    def smu(self, channel: int) -> SMUChannel:
        ch = self.channel(channel)
        if not isinstance(ch, SMUChannel):
            raise UnsupportedFeatureError(f"channel {channel} is not an SMU")
        return ch

    def load(self, channel: int) -> ElectronicLoadChannel:
        ch = self.channel(channel)
        if not isinstance(ch, ElectronicLoadChannel):
            raise UnsupportedFeatureError(f"channel {channel} is not an electronic load")
        return ch

    # Optional wrapper APIs around type-specific channels.
    def set_smu_mode(self, channel: int, mode: Literal["voltage", "current"]) -> None:
        self.smu(channel).set_smu_mode(mode)

    def get_smu_mode(self, channel: int) -> Literal["voltage", "current"]:
        return self.smu(channel).get_smu_mode()

    def configure_smu_voltage_priority(self, channel: int, voltage: float, current_limit: float, **kw: Any) -> None:
        self.smu(channel).configure_voltage_priority(voltage, current_limit, **kw)

    def configure_smu_current_priority(self, channel: int, current: float, voltage_limit: float, **kw: Any) -> None:
        self.smu(channel).configure_current_priority(current, voltage_limit, **kw)

    def set_load_mode(self, channel: int, mode: Literal["cc", "cv", "cr", "cp"]) -> None:
        self.load(channel).set_load_mode(mode)

    def get_load_mode(self, channel: int) -> Literal["cc", "cv", "cr", "cp"]:
        return self.load(channel).get_load_mode()

    def configure_load_cc(self, channel: int, current: float, *, input_on: bool = False, verify: bool = True, **_: object) -> None:
        self.load(channel).configure_cc(current, input_on=input_on, verify=verify)

    def set_power_outputs(self, channels: Sequence[int], enabled: bool) -> None:
        for ch in channels:
            self.power_supply(ch).set_output(enabled)

    def set_load_inputs(self, channels: Sequence[int], enabled: bool) -> None:
        for ch in channels:
            self.load(ch).set_input(enabled)

    def set_channel_enabled(self, channels: Sequence[int], enabled: bool) -> None:
        for ch in channels:
            chan = self.channel(ch)
            if isinstance(chan, ElectronicLoadChannel):
                chan.set_input(enabled)
            elif isinstance(chan, PowerSupplyChannel):
                chan.set_output(enabled)
            else:
                raise UnsupportedFeatureError(f"channel {ch} cannot be enabled")

    def measure_all(self) -> dict[int, Measurement]:
        return {ch: self._measure_channel(ch) for ch in self.channels}

    def _timestamp(self) -> tuple[str, float]:
        ts = time.time()
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(), ts

    def _measure_power(self, channel: int) -> PowerMeasurement:
        iso, ts = self._timestamp()
        capabilities = self.channel(channel).capabilities
        if capabilities.supports_power_measurement:
            value = float(self.query_scpi(f"MEAS:POW? {format_channel_list(channel)}"))
            return PowerMeasurement(channel, value, "instrument", iso, ts)

        try:
            voltage = float(self.query_scpi(f"MEAS:VOLT? {format_channel_list(channel)}"))
            current = float(self.query_scpi(f"MEAS:CURR? {format_channel_list(channel)}"))
        except Exception:
            return PowerMeasurement(channel, None, "unavailable", iso, ts)
        return PowerMeasurement(channel, voltage * current, "calculated", iso, ts)

    def _measure_channel(self, channel: int) -> Measurement:
        iso, ts = self._timestamp()
        voltage: float | None = None
        current: float | None = None
        with suppress(Exception):
            voltage = float(self.query_scpi(f"MEAS:VOLT? {format_channel_list(channel)}"))
        with suppress(Exception):
            current = float(self.query_scpi(f"MEAS:CURR? {format_channel_list(channel)}"))

        capabilities = self.channel(channel).capabilities
        if capabilities.supports_power_measurement:
            power = self._measure_power(channel)
        elif voltage is not None and current is not None:
            power = PowerMeasurement(channel, voltage * current, "calculated", iso, ts)
        else:
            power = PowerMeasurement(channel, None, "unavailable", iso, ts)
        return Measurement(channel, voltage, current, power.power_W, power.power_source, iso, ts)

    def clear_protection(
        self,
        channel: int,
        *,
        restore_output: bool = False,
        force_output_off_first: bool = True,
        verify_cleared: bool = True,
    ) -> ProtectionClearResult:
        return self.channel(channel).clear_protection(
            restore_output=restore_output,
            force_output_off_first=force_output_off_first,
            verify_cleared=verify_cleared,
        )

    def _status_channel_list(self, channel: int | None) -> str:
        if channel is not None:
            return format_channel_list(channel)
        if not self.channels:
            raise InvalidChannelError("no installed N6700 channels were discovered")
        return format_channel_list(sorted(self.channels))

    @staticmethod
    def _parse_status_response(raw: str) -> int | str:
        stripped = raw.strip()
        if "," in stripped:
            return stripped
        return int(stripped)

    def get_operation_status(self, channel: int | None = None) -> OperationStatus:
        chanlist = self._status_channel_list(channel)
        raw = self.query_scpi(f"STAT:OPER:COND? {chanlist}")
        return OperationStatus(self._parse_status_response(raw))

    def get_questionable_status(self, channel: int | None = None) -> QuestionableStatus:
        chanlist = self._status_channel_list(channel)
        raw = self.query_scpi(f"STAT:QUES:COND? {chanlist}")
        return QuestionableStatus(self._parse_status_response(raw))

    def shutdown_all(self) -> ShutdownResult:
        results: list[ShutdownChannelResult] = []
        for ch_num in sorted(self.channels):
            try:
                ch = self.channel(ch_num)
                if isinstance(ch, ElectronicLoadChannel):
                    ch.input_off()
                elif isinstance(ch, PowerSupplyChannel):
                    ch.output_off()
                results.append(ShutdownChannelResult(ch_num, True, True))
            except Exception as exc:
                results.append(ShutdownChannelResult(ch_num, True, False, str(exc)))
        return ShutdownResult(tuple(results))

    def audit(self, record: AuditRecord) -> None:
        if self.audit_log_path is None:
            return
        with self.audit_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record.__dict__, default=str) + "\n")

    def close(self) -> None:
        self.transport.close()


class _NullLock:
    def __enter__(self) -> _NullLock:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None
