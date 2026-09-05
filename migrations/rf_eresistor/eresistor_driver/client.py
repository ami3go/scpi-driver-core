"""High-level synchronous Python API for the E-Resistor board."""
from __future__ import annotations

import json
import logging
import math
import re
import signal
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from .calibration import (
    calibration_age_hours,
    load_calibration_json,
    merge_calibrations,
    parse_begin_end_calibration,
    parse_compact_calibration,
    save_calibration_json,
    validate_device_calibration,
)
from .exceptions import CalibrationError, ConnectionError, EResistorError, HttpApiError, ScpiError, SimulationError
from .http_api import EResistorHttpApi
from .logging_utils import AuditLogger
from .metrics import MetricsRegistry
from .models import (
    BoardInfo,
    CalibrationConfig,
    ConnectionLossPolicy,
    ConnectionState,
    DeviceCalibration,
    DeviceProfile,
    OutputSnapshot,
    ReconnectStatePolicy,
    SafetyConfig,
    SetResistanceResult,
    SetTemperatureResult,
    ShutdownPolicy,
    WatchdogConfig,
)
from .profile import load_profile, save_profile
from .resistance import ResistanceSolver
from .scpi import ScpiTransport
from .simulation import CurveProfile, CurveSimulation
from .state_persistence import load_snapshot, save_snapshot
from .temperature import TemperatureTable
from .validation import CHANNEL_COUNT, normalize_all_masks, normalize_mask, parse_idn, validate_channel

_LOG = logging.getLogger(__name__)


class EResistorClient:
    """High-level E-Resistor board driver.

    The client is synchronous and thread-safe for SCPI access. Background
    keepalive/watchdog can be enabled through ``watchdog.enabled`` or the
    convenience constructor arguments.
    """

    def __init__(
        self,
        host: str,
        *,
        scpi_port: int = 5025,
        http_port: int = 80,
        timeout: float = 2.0,
        retries: int = 2,
        safety: SafetyConfig | None = None,
        watchdog: WatchdogConfig | None = None,
        calibration_config: CalibrationConfig | None = None,
        reconnect_state_policy: ReconnectStatePolicy = ReconnectStatePolicy.VERIFY_AND_HOLD,
        shutdown_policy: ShutdownPolicy = ShutdownPolicy.ALL_OFF,
        state_persistence_file: str | None = None,
        min_firmware_version: str | None = None,
        firmware_check_on_connect: bool = False,
        audit_log_file: str | None = None,
        connection_state_callback: Callable[[ConnectionState], None] | None = None,
    ) -> None:
        self.host = host
        self.scpi_port = scpi_port
        self.http_port = http_port
        self.timeout = timeout
        self.retries = retries
        self.safety = safety or SafetyConfig()
        self.watchdog_config = watchdog or WatchdogConfig(enabled=False)
        self.calibration_config = calibration_config or CalibrationConfig()
        self.reconnect_state_policy = reconnect_state_policy
        self.shutdown_policy = shutdown_policy
        self.state_persistence_file = state_persistence_file
        self.min_firmware_version = min_firmware_version
        self.firmware_check_on_connect = firmware_check_on_connect
        self._connection_state_callback = connection_state_callback

        self.metrics = MetricsRegistry()
        self.audit = AuditLogger(audit_log_file)
        self.scpi = ScpiTransport(
            host,
            scpi_port,
            timeout=timeout,
            retries=retries,
            state_callback=self._on_transport_state,
        )
        self.http = EResistorHttpApi(host, http_port, timeout=timeout)
        self.calibration: DeviceCalibration | None = None
        self.solver: ResistanceSolver | None = None
        self.temperature_tables: dict[int | str, TemperatureTable] = {}
        self._last_known_masks: dict[int, str] = {ch: "0000" for ch in range(1, CHANNEL_COUNT + 1)}
        self._last_snapshot: OutputSnapshot | None = None
        self._watchdog_stop = threading.Event()
        self._watchdog_thread: threading.Thread | None = None
        self._state = ConnectionState.DISCONNECTED
        self._state_lock = threading.RLock()
        self._simulation_channels: set[int] = set()
        self._simulation_lock = threading.RLock()

    @classmethod
    def from_profile(cls, profile: DeviceProfile) -> "EResistorClient":
        return cls(
            host=profile.host,
            scpi_port=profile.scpi_port,
            http_port=profile.http_port,
            timeout=profile.default_timeout_s,
            safety=profile.safety,
            watchdog=profile.watchdog,
            calibration_config=profile.calibration,
            reconnect_state_policy=profile.reconnect.state_policy,
            shutdown_policy=profile.shutdown_policy,
            state_persistence_file=profile.state_persistence_file,
            min_firmware_version=profile.min_firmware_version,
            firmware_check_on_connect=profile.firmware_check_on_connect,
            audit_log_file=profile.logging.audit_log_file,
        )

    def to_profile(self, *, device_name: str | None = None) -> DeviceProfile:
        return DeviceProfile(
            device_name=device_name,
            host=self.host,
            scpi_port=self.scpi_port,
            http_port=self.http_port,
            default_timeout_s=self.timeout,
            min_firmware_version=self.min_firmware_version,
            firmware_check_on_connect=self.firmware_check_on_connect,
            safety=self.safety,
            watchdog=self.watchdog_config,
            calibration=self.calibration_config,
            state_persistence_file=self.state_persistence_file,
            shutdown_policy=self.shutdown_policy,
        )

    def save_profile(self, path: str | Path, *, device_name: str | None = None) -> None:
        save_profile(self.to_profile(device_name=device_name), path)

    def __enter__(self) -> "EResistorClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def connection_state(self) -> ConnectionState:
        with self._state_lock:
            return self._state

    def _on_transport_state(self, state: ConnectionState) -> None:
        with self._state_lock:
            self._state = state
        if self._connection_state_callback:
            self._connection_state_callback(state)

    # ---------------------------------------------------------------------
    # Connection and system API
    # ---------------------------------------------------------------------
    def connect(self) -> None:
        self.scpi.connect()
        idn = self.idn()
        serial, firmware = parse_idn(idn)
        if self.firmware_check_on_connect and self.min_firmware_version and firmware:
            if _version_lt(firmware, self.min_firmware_version):
                raise EResistorError(
                    f"Firmware {firmware} is older than required {self.min_firmware_version}; refusing to operate"
                )
        if self.calibration_config.local_cache_file and not self.calibration_config.refresh_on_connect:
            try:
                self.load_calibration(self.calibration_config.local_cache_file)
            except Exception as exc:
                _LOG.warning("Failed to load calibration cache: %s", exc)
        if self.calibration_config.auto_download and (self.calibration is None or self.calibration_config.refresh_on_connect):
            try:
                self.download_calibration()
            except Exception as exc:
                _LOG.warning("Automatic calibration download failed: %s", exc)
        self._update_last_known_masks_from_device()
        if self.watchdog_config.enabled:
            self.start_watchdog()

    def close(self) -> None:
        self.stop_watchdog()
        try:
            if self.shutdown_policy == ShutdownPolicy.ALL_OFF:
                try:
                    self.all_off()
                except Exception as exc:
                    _LOG.warning("ALL:OFF during close failed: %s", exc)
            elif self.shutdown_policy == ShutdownPolicy.RESTORE_SNAPSHOT and self._last_snapshot:
                try:
                    self.restore_output_snapshot(self._last_snapshot)
                except Exception as exc:
                    _LOG.warning("Snapshot restore during close failed: %s", exc)
        finally:
            self.scpi.close()
            self.audit.close()

    def safe_connect(self, *, all_off_on_connect: bool = False) -> None:
        self.connect()
        if all_off_on_connect:
            self.all_off()

    def safe_shutdown(self, *, all_off: bool = True) -> None:
        if all_off:
            self.all_off()
        self.close()

    def register_signal_handlers(self) -> None:
        def handler(signum, frame):
            _LOG.warning("Received signal %s; shutting down E-Resistor client", signum)
            self.close()
            raise SystemExit(128 + int(signum))
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def idn(self) -> str:
        return self.query("*IDN?")

    def ping(self) -> bool:
        try:
            return self.http.ping()
        except Exception:
            try:
                return bool(self.idn())
            except Exception:
                return False

    def identify(self, duration_s: float = 5.0) -> str:
        # Firmware currently exposes blink through HTTP; duration_s kept for API compatibility.
        return self.http.identify_led()

    def get_serial(self) -> str:
        try:
            return self.query("SYST:SER?")
        except ScpiError:
            serial, _fw = parse_idn(self.idn())
            return serial or ""

    def get_firmware_version(self) -> str:
        try:
            return self.query("FIRM:VERS?")
        except ScpiError:
            _serial, fw = parse_idn(self.idn())
            return fw or ""

    def get_firmware_build(self) -> str:
        return self.query("FIRM:BUILD?")

    def clear_errors(self) -> str:
        return self.query("SYST:ERR:CLEAR")

    def get_error(self) -> str:
        return self.query("SYST:ERR?")

    def get_status(self) -> dict[str, str]:
        text = self.query("SYST:STAT?")
        return _parse_key_value_text(text)

    def get_state(self) -> str:
        return self.query("STATE?")

    def query(self, command: str, *, multiline_until: str | None = None) -> str:
        self.metrics.inc("scpi_commands_total")
        with self.metrics.timeit("scpi_command_duration_seconds"):
            response = self.scpi.request(command, multiline_until=multiline_until)
        if _is_state_changing(command):
            self.audit.log_command(command, response, "ok", host=self.host)
        return response

    # ---------------------------------------------------------------------
    # Watchdog, keepalive, recovery
    # ---------------------------------------------------------------------
    def start_watchdog(self) -> None:
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return
        self._watchdog_stop.clear()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, name="EResistorWatchdog", daemon=True)
        self._watchdog_thread.start()

    def stop_watchdog(self) -> None:
        self._watchdog_stop.set()
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=2.0)
        self._watchdog_thread = None

    def _watchdog_loop(self) -> None:
        cfg = self.watchdog_config
        while not self._watchdog_stop.wait(cfg.keepalive_interval_s):
            try:
                self.query(cfg.keepalive_command)
                self.metrics.inc("keepalive_ok_total")
            except Exception as exc:
                self.metrics.inc("keepalive_fail_total")
                _LOG.warning("Keepalive failed: %s", exc)
                self._handle_connection_loss(exc)

    def _handle_connection_loss(self, exc: Exception) -> None:
        self._on_transport_state(ConnectionState.LOST)
        if self.safety.connection_loss_policy == ConnectionLossPolicy.ATTEMPT_ALL_OFF:
            try:
                self.all_off()
            except Exception:
                _LOG.error("Connection lost and ALL:OFF could not be sent. Firmware-side watchdog is required for true fail-safe output.")
        elif self.safety.connection_loss_policy == ConnectionLossPolicy.ATTEMPT_SAFE_RESISTANCE:
            if self.safety.safe_resistance_ohm is not None:
                try:
                    self.set_resistances({ch: self.safety.safe_resistance_ohm for ch in range(1, CHANNEL_COUNT + 1)})
                except Exception:
                    _LOG.error("Connection lost and safe resistance could not be applied")
        if self.watchdog_config.on_fail == "reconnect":
            try:
                self.scpi.reconnect()
                self._recover_state_after_reconnect()
            except Exception as rec_exc:
                _LOG.error("Reconnect failed: %s", rec_exc)

    def _recover_state_after_reconnect(self) -> None:
        try:
            device_masks = self.get_all_masks()
        except Exception as exc:
            _LOG.warning("Could not read state after reconnect: %s", exc)
            return
        if device_masks != self._last_known_masks:
            _LOG.warning("Device state differs from last known state after reconnect", extra={"device_masks": device_masks, "last_known": self._last_known_masks})
            if self.reconnect_state_policy == ReconnectStatePolicy.RESTORE_LAST:
                self.set_all_masks([self._last_known_masks[ch] for ch in range(1, CHANNEL_COUNT + 1)])
            elif self.reconnect_state_policy == ReconnectStatePolicy.ALL_OFF:
                self.all_off()
            elif self.reconnect_state_policy == ReconnectStatePolicy.VERIFY_AND_HOLD:
                self._last_known_masks = device_masks

    # ---------------------------------------------------------------------
    # Mask control
    # ---------------------------------------------------------------------
    def set_mask(self, channel: int, mask: int | str, *, force: bool = False) -> str:
        channel = validate_channel(channel)
        self._ensure_channel_available(channel, force=force)
        mask_s = normalize_mask(mask)
        response = self.query(f"CH{channel}:MASK {mask_s}")
        if response.strip().upper() != "OK":
            raise ScpiError("Unexpected response for mask set", command=f"CH{channel}:MASK {mask_s}", response=response)
        self._last_known_masks[channel] = mask_s
        self._persist_snapshot_if_configured()
        return mask_s

    def get_mask(self, channel: int) -> str:
        channel = validate_channel(channel)
        response = self.query(f"CH{channel}:MASK?").strip()
        mask = normalize_mask(response.split(",")[0].split("=")[-1])
        self._last_known_masks[channel] = mask
        return mask

    def get_all_masks(self) -> dict[int, str]:
        state = self.get_state()
        masks = _parse_state_masks(state)
        if not masks:
            masks = {ch: self.get_mask(ch) for ch in range(1, CHANNEL_COUNT + 1)}
        self._last_known_masks.update(masks)
        return masks

    def set_all_masks(self, masks: Sequence[int | str], *, force: bool = False) -> dict[int, str]:
        masks_s = normalize_all_masks(list(masks))
        if not force:
            for ch in range(1, CHANNEL_COUNT + 1):
                self._ensure_channel_available(ch, force=False)
        cmd = "ROUT:ALL:MASK " + ",".join(masks_s)
        response = self.query(cmd)
        if response.strip().upper() != "OK":
            raise ScpiError("Unexpected response for ROUT:ALL:MASK", command=cmd, response=response)
        self._last_known_masks = {ch: masks_s[ch - 1] for ch in range(1, CHANNEL_COUNT + 1)}
        self._persist_snapshot_if_configured()
        return dict(self._last_known_masks)

    def set_masks(self, masks: Mapping[int, int | str], *, force: bool = False) -> dict[int, str]:
        current = self.get_all_masks()
        for ch, mask in masks.items():
            ch_i = validate_channel(int(ch))
            if not force:
                self._ensure_channel_available(ch_i, force=False)
            current[ch_i] = normalize_mask(mask)
        return self.set_all_masks([current[ch] for ch in range(1, CHANNEL_COUNT + 1)], force=force)

    def all_off(self) -> str:
        response = self.query("ALL:OFF")
        if response.strip().upper() not in {"OK", "0"}:
            raise ScpiError("Unexpected response for ALL:OFF", command="ALL:OFF", response=response)
        self._last_known_masks = {ch: "0000" for ch in range(1, CHANNEL_COUNT + 1)}
        self._persist_snapshot_if_configured()
        return response

    # ---------------------------------------------------------------------
    # Calibration
    # ---------------------------------------------------------------------
    def list_calibration_files(self) -> str:
        try:
            return self.query("CAL:FILES?")
        except Exception:
            return self.http.list_calibration_files()

    def download_calibration(self) -> DeviceCalibration:
        errors: list[str] = []
        cal: DeviceCalibration | None = None
        try:
            text = self.query("CAL:RES?")
            cal = parse_compact_calibration(text, source="scpi_compact")
        except Exception as exc:
            errors.append(f"SCPI CAL:RES? failed: {exc}")
        if cal is None:
            try:
                text = self.query("CAL:ALL:FILES?", multiline_until="#END ALL")
                cal = parse_begin_end_calibration(text, source="scpi_file")
            except Exception as exc:
                errors.append(f"SCPI CAL:ALL:FILES? failed: {exc}")
        if cal is None:
            try:
                text = self.http.download_all_calibration()
                cal = parse_begin_end_calibration(text, source="http_file")
            except Exception as exc:
                errors.append(f"HTTP download_all failed: {exc}")
        if cal is None:
            raise CalibrationError("Could not download calibration. " + " | ".join(errors))
        cal.serial = _none_if_empty(self.get_serial())
        cal.firmware_version = _none_if_empty(self.get_firmware_version())
        cal.mark_downloaded_now()
        validate_device_calibration(cal, require_all_channels=False)
        self.calibration = cal
        self.solver = ResistanceSolver(cal, self.safety)
        if self.calibration_config.local_cache_file:
            save_calibration_json(cal, self.calibration_config.local_cache_file)
        return cal

    def download_channel_calibration(self, channel: int) -> DeviceCalibration:
        channel = validate_channel(channel)
        errors: list[str] = []
        try:
            text = self.query(f"CAL:FILE? CH{channel}", multiline_until=f"#END CH{channel}")
            cal = parse_begin_end_calibration(text, source="scpi_file")
            if channel not in cal.channels and 1 in cal.channels:
                cal.channels[channel] = cal.channels.pop(1)
                cal.channels[channel].channel = channel
            return cal
        except Exception as exc:
            errors.append(str(exc))
        try:
            text = self.http.download_channel_calibration(channel)
            cal = parse_begin_end_calibration(text, source="http_file")
            if channel not in cal.channels and 1 in cal.channels:
                cal.channels[channel] = cal.channels.pop(1)
                cal.channels[channel].channel = channel
            return cal
        except Exception as exc:
            errors.append(str(exc))
        raise CalibrationError(f"Could not download CH{channel} calibration: {' | '.join(errors)}")

    def save_calibration(self, path: str | Path) -> None:
        if not self.calibration:
            raise CalibrationError("No calibration loaded")
        save_calibration_json(self.calibration, path)

    def load_calibration(self, path: str | Path) -> DeviceCalibration:
        cal = load_calibration_json(path)
        age = calibration_age_hours(cal)
        if self.calibration_config.max_age_hours is not None and age is not None and age > self.calibration_config.max_age_hours:
            msg = f"Calibration cache age {age:.1f} h exceeds max_age_hours={self.calibration_config.max_age_hours}"
            if self.calibration_config.on_stale == "refuse_operations":
                raise CalibrationError(msg)
            _LOG.warning(msg)
        self.calibration = cal
        self.solver = ResistanceSolver(cal, self.safety)
        return cal

    def build_resistance_cache(self) -> None:
        self._ensure_solver().build_cache()

    def clear_resistance_cache(self) -> None:
        if self.solver:
            self.solver.clear_cache()

    def get_resistance_for_mask(self, channel: int, mask: int | str) -> float:
        return self._ensure_solver().equivalent_resistance(channel, mask)

    def find_closest_resistance(self, channel: int, resistance_ohm: float, *, allow_closest_out_of_range: bool = False) -> SetResistanceResult:
        return self._ensure_solver().find_closest(channel, resistance_ohm, allow_closest_out_of_range=allow_closest_out_of_range)

    def _ensure_solver(self) -> ResistanceSolver:
        if self.solver is None:
            if self.calibration_config.auto_download:
                self.download_calibration()
            else:
                raise CalibrationError("No calibration loaded")
        assert self.solver is not None
        return self.solver

    # ---------------------------------------------------------------------
    # Resistance and temperature control
    # ---------------------------------------------------------------------
    def set_resistance(
        self,
        channel: int,
        resistance_ohm: float,
        *,
        allow_closest_out_of_range: bool = False,
        force: bool = False,
    ) -> SetResistanceResult:
        channel = validate_channel(channel)
        self._ensure_channel_available(channel, force=force)
        result = self.find_closest_resistance(channel, resistance_ohm, allow_closest_out_of_range=allow_closest_out_of_range)
        self.set_mask(channel, result.mask, force=force)
        return result

    def preview_set_resistances(self, values: Mapping[int, float] | Sequence[float | None]) -> list[SetResistanceResult]:
        normalized = _normalize_bulk_values(values)
        return [self.find_closest_resistance(ch, ohm) for ch, ohm in normalized.items()]

    def set_resistances(
        self,
        values: Mapping[int, float] | Sequence[float | None],
        *,
        atomic: bool = True,
        force: bool = False,
    ) -> list[SetResistanceResult]:
        normalized = _normalize_bulk_values(values)
        if not normalized:
            return []
        for ch in normalized:
            self._ensure_channel_available(ch, force=force)
        results = [self.find_closest_resistance(ch, ohm) for ch, ohm in normalized.items()]
        if atomic:
            current = self.get_all_masks()
            for result in results:
                current[result.channel] = result.mask
            self.set_all_masks([current[ch] for ch in range(1, CHANNEL_COUNT + 1)], force=force)
        else:
            for result in results:
                self.set_mask(result.channel, result.mask, force=force)
        return results

    def load_temperature_table(self, channel: int, path: str | Path) -> TemperatureTable:
        channel = validate_channel(channel)
        table = TemperatureTable.from_csv(path)
        self.temperature_tables[channel] = table
        return table

    def load_temperature_table_for_all(self, path: str | Path) -> TemperatureTable:
        table = TemperatureTable.from_csv(path)
        self.temperature_tables["default"] = table
        return table

    def get_temperature_table(self, channel: int) -> TemperatureTable:
        channel = validate_channel(channel)
        table = self.temperature_tables.get(channel) or self.temperature_tables.get("default")
        if table is None:
            raise CalibrationError(f"No temperature table loaded for CH{channel}")
        return table

    def clear_temperature_table(self, channel: int) -> None:
        channel = validate_channel(channel)
        self.temperature_tables.pop(channel, None)

    def set_temperature(
        self,
        channel: int,
        temperature_c: float,
        *,
        interpolation: str = "linear",
        allow_extrapolation: bool = False,
        force: bool = False,
    ) -> SetTemperatureResult:
        table = self.get_temperature_table(channel)
        requested_r = table.resistance_at(temperature_c, mode=interpolation, allow_extrapolation=allow_extrapolation)
        res = self.set_resistance(channel, requested_r, force=force)
        return SetTemperatureResult(
            channel=channel,
            requested_temperature_c=float(temperature_c),
            interpolated_resistance_ohm=requested_r,
            calculated_resistance_ohm=res.calculated_ohm,
            resistance_error_ohm=res.error_ohm,
            resistance_error_percent=res.error_percent,
            mask=res.mask,
            resistance_result=res,
        )

    # ---------------------------------------------------------------------
    # Simulation
    # ---------------------------------------------------------------------
    def create_curve_simulation(
        self,
        channel: int,
        path: str | Path,
        *,
        input_type: str | None = None,
        repeat: int | None = 1,
        on_error: str = "stop_and_all_off",
        max_total_duration_s: float | None = None,
        state_file: str | None = None,
    ) -> CurveSimulation:
        channel = validate_channel(channel)
        profile = CurveProfile.from_csv(path, input_type=input_type)
        return CurveSimulation(
            profile,
            channel=channel,
            apply_callback=self._simulation_apply_callback,
            repeat=repeat,
            on_error=on_error,
            max_total_duration_s=max_total_duration_s,
            state_file=state_file,
            all_off_callback=self.all_off,
        )

    def run_curve(self, channel: int, path: str | Path, *, input_type: str | None = None, repeat: int | None = 1, blocking: bool = True) -> CurveSimulation:
        sim = self.create_curve_simulation(channel, path, input_type=input_type, repeat=repeat)
        with self._simulation_channel(channel):
            if blocking:
                sim.run()
            else:
                sim.start()
        return sim

    def run_multi_channel_curve(
        self,
        channel_profiles: Mapping[int, str | Path],
        *,
        repeat: int | None = 1,
        synchronized: bool = True,
    ) -> list[CurveSimulation]:
        # Basic implementation: start independent simulations. Synchronized exact multi-channel stepping
        # can be added above this using ROUT:ALL:MASK after merging time grids.
        sims = [self.create_curve_simulation(ch, path, repeat=repeat) for ch, path in channel_profiles.items()]
        if synchronized:
            for sim in sims:
                sim.start()
            for sim in sims:
                sim.join()
        else:
            for sim in sims:
                sim.start()
        return sims

    def _simulation_apply_callback(self, channel: int, value_type: str, value: float) -> SetResistanceResult:
        with self._simulation_channel(channel):
            if value_type == "temperature":
                return self.set_temperature(channel, value, force=True).resistance_result
            if value_type == "resistance":
                return self.set_resistance(channel, value, force=True)
            raise SimulationError(f"Unsupported simulation value_type {value_type!r}")

    def _simulation_channel(self, channel: int):
        client = self
        class _Guard:
            def __enter__(self_inner):
                with client._simulation_lock:
                    if channel in client._simulation_channels:
                        # Reentrant use from callback is allowed by releasing only if we added.
                        self_inner.added = False
                    else:
                        client._simulation_channels.add(channel)
                        self_inner.added = True
                return self_inner
            def __exit__(self_inner, exc_type, exc, tb):
                if getattr(self_inner, "added", False):
                    with client._simulation_lock:
                        client._simulation_channels.discard(channel)
        return _Guard()

    def _ensure_channel_available(self, channel: int, *, force: bool) -> None:
        if force:
            return
        with self._simulation_lock:
            if channel in self._simulation_channels:
                raise SimulationError(f"CH{channel} is locked by a running simulation; use force=True to override")

    # ---------------------------------------------------------------------
    # Snapshot, export, verification
    # ---------------------------------------------------------------------
    def get_output_snapshot(self) -> OutputSnapshot:
        snapshot = OutputSnapshot(masks=self.get_all_masks())
        self._last_snapshot = snapshot
        return snapshot

    def restore_output_snapshot(self, snapshot: OutputSnapshot) -> dict[int, str]:
        return self.set_all_masks([snapshot.masks[ch] for ch in range(1, CHANNEL_COUNT + 1)])

    def verify_mask(self, channel: int, expected_mask: int | str) -> bool:
        return self.get_mask(channel) == normalize_mask(expected_mask)

    def verify_all_masks(self, expected_masks: Sequence[int | str]) -> bool:
        expected = {ch: normalize_mask(expected_masks[ch - 1]) for ch in range(1, CHANNEL_COUNT + 1)}
        return self.get_all_masks() == expected

    def get_all_resistances(self) -> dict[int, float]:
        masks = self.get_all_masks()
        return {ch: self.get_resistance_for_mask(ch, mask) for ch, mask in masks.items()}

    def export_calibration_json(self, path: str | Path) -> None:
        self.save_calibration(path)

    def export_calibration_csv(self, path: str | Path) -> None:
        if not self.calibration:
            raise CalibrationError("No calibration loaded")
        lines = ["channel,bit_index,mosfet_name,resistance_ohm"]
        for ch in sorted(self.calibration.channels):
            for b in sorted(self.calibration.channels[ch].branches, key=lambda x: x.bit_index):
                lines.append(f"{ch},{b.bit_index},{b.mosfet_name},{b.resistance_ohm:.12g}")
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def export_resistance_lookup(self, channel: int, path: str | Path) -> None:
        solver = self._ensure_solver()
        solver.build_cache(channel)
        rows = ["mask,resistance_ohm,active_bits"]
        for cand in solver._cache[validate_channel(channel)]:  # internal cache export helper
            rows.append(f"{cand.mask},{cand.resistance_ohm:.12g},{cand.active_count}")
        Path(path).write_text("\n".join(rows) + "\n", encoding="utf-8")

    def _update_last_known_masks_from_device(self) -> None:
        try:
            self._last_known_masks = self.get_all_masks()
        except Exception as exc:
            _LOG.debug("Could not update masks from device: %s", exc)

    def _persist_snapshot_if_configured(self) -> None:
        if self.state_persistence_file:
            save_snapshot(self.state_persistence_file, OutputSnapshot(self._last_known_masks))


def _parse_key_value_text(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in re.split(r"[;,]\s*", text.strip()):
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _parse_state_masks(text: str) -> dict[int, str]:
    masks: dict[int, str] = {}
    for m in re.finditer(r"CH\s*(\d+)\s*=\s*([0-9A-Fa-fx]{1,6})", text):
        ch = int(m.group(1))
        if 1 <= ch <= CHANNEL_COUNT:
            masks[ch] = normalize_mask(m.group(2))
    return masks


def _normalize_bulk_values(values: Mapping[int, float] | Sequence[float | None]) -> dict[int, float]:
    result: dict[int, float] = {}
    if isinstance(values, Mapping):
        for ch, ohm in values.items():
            result[validate_channel(int(ch))] = float(ohm)
    else:
        for idx, ohm in enumerate(values):
            if ohm is None:
                continue
            result[validate_channel(idx + 1)] = float(ohm)
    return result


def _is_state_changing(command: str) -> bool:
    u = command.strip().upper()
    return any(u.startswith(prefix) for prefix in ["CH", "ROUT", "ALL:OFF", "OUTP", "CAL:"] if not u.endswith("?"))


def _none_if_empty(value: str) -> str | None:
    return value if value else None


def _version_lt(found: str, required: str) -> bool:
    def parts(v: str) -> list[int]:
        nums = re.findall(r"\d+", v)
        return [int(n) for n in nums[:4]] or [0]
    a = parts(found)
    b = parts(required)
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a < b
