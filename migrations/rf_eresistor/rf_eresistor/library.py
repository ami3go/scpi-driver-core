"""Robot Framework adapter for :mod:`eresistor_driver`.

The adapter deliberately returns Robot-friendly dictionaries and lists while
keeping all transport, validation, solver and safety behaviour in the proven
Python driver bundled with this distribution.

Every public keyword is wrapped (see ``_evidenced`` below) with an RFDS-008
evidence operation record, and the connected client's SCPI/HTTP calls are
traced as protocol evidence by wrapping the instance after ``connect()`` —
see ``rf_eresistor/evidence.py`` and ``docs/logging_and_evidence.md``. Pass
``evidence_enabled=${FALSE}`` to disable it.
"""
from __future__ import annotations

import functools
import inspect
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from robot.api import logger
from robot.api.deco import keyword, library

from eresistor_driver import EResistorClient, discover_boards, discover_boards_auto
from eresistor_driver.profile import load_profile
from eresistor_driver.validation import normalize_mask

from . import evidence as _evidence


def _robot_value(value: Any) -> Any:
    if is_dataclass(value):
        return _robot_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(k): _robot_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_robot_value(v) for v in value]
    return value


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "on", "1"}:
        return True
    if text in {"false", "no", "off", "0", "", "none"}:
        return False
    raise ValueError(f"Expected Boolean value, got {value!r}")


def _evidenced(func: Callable) -> Callable:
    """Wrap a keyword method with an RFDS-008 evidence operation record.

    Reads ``self._evidence``/``self._session_alias`` on the bound instance,
    binds ``*args``/``**kwargs`` to parameter names for a readable argument
    record, and records success/failure/duration around the call.
    ``Disconnect From EResistor`` additionally finalizes the run (writes
    ``run_summary.json`` + ``evidence_manifest.json``) once its own operation
    record has been written. Every other keyword — including the generic
    ``Disconnect``, which calls the same underlying decorated method — leaves
    finalization alone.

    Must sit *below* ``@keyword(...)`` in the decorator stack (closest to
    ``def``) — it reads ``wrapper.robot_name`` at call time via closure,
    which ``@keyword`` sets on the object this function returns once the
    class body finishes executing, well before any instance method call
    happens.
    """
    signature = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(self: EResistorLibrary, *args: Any, **kwargs: Any) -> Any:
        capability = getattr(wrapper, "robot_name", None) or func.__name__.replace("_", " ").title()
        run = self._ensure_evidence()
        bound = signature.bind_partial(self, *args, **kwargs)
        bound.apply_defaults()
        arguments = {key: value for key, value in bound.arguments.items() if key != "self"}
        status = "PASS"
        try:
            with run.record_operation(capability, arguments=arguments, session_alias=self._session_alias) as op:
                result = func(self, *args, **kwargs)
                op.set_result(result)
            return result
        except Exception:
            status = "FAIL"
            raise
        finally:
            if capability == "Disconnect From EResistor":
                run.finalize(status=status)
                self._evidence = None

    return wrapper


@library(scope="SUITE", version="26.03", auto_keywords=False)
class EResistorLibrary:
    """Control an 8-channel E-Resistor from Robot Framework.

    Import arguments configure the default connection. No network access occurs
    until ``Connect To EResistor`` is called. The library closes the connection
    at suite end; the default underlying shutdown policy switches all channels
    off.
    """

    ROBOT_LIBRARY_DOC_FORMAT = "ROBOT"

    def __init__(self, host: str = "192.168.0.55", scpi_port: int = 5025,
                 http_port: int = 80, timeout: float = 2.0, retries: int = 2,
                 profile: str | None = None, audit_log_file: str | None = None,
                 evidence_enabled: Any = True, session_alias: Any = "default"):
        self._settings = dict(host=str(host), scpi_port=int(scpi_port),
                              http_port=int(http_port), timeout=float(timeout),
                              retries=int(retries), audit_log_file=audit_log_file)
        self._profile = profile
        self._client: EResistorClient | None = None
        self.ROBOT_LIBRARY_LISTENER = self
        self._evidence_enabled = _bool(evidence_enabled)
        self._session_alias = str(session_alias)
        self._evidence: Any = None

    def _ensure_evidence(self) -> Any:
        """Lazily create (or return) this session's :class:`evidence.EvidenceRun`.

        Created on first keyword call rather than in ``__init__`` so
        constructing the library for argument validation alone never touches
        disk.
        """
        if self._evidence is None:
            if self._evidence_enabled:
                self._evidence = _evidence.EvidenceRun(driver_id="rf_eresistor", activity="session")
            else:
                self._evidence = _evidence.NullEvidenceRun()
        return self._evidence

    def _trace_client_protocol(self, client: EResistorClient) -> None:
        """Wrap ``client.query`` and ``client.http.get_text`` so every SCPI/HTTP
        exchange is recorded as protocol evidence. Instance-level wrapping only
        — ``eresistor_driver`` itself (used standalone via its own CLI) is
        never modified. See ``evidence.py``'s module docstring."""
        run = self._evidence
        if run is None:
            return
        original_query = client.query

        def _traced_query(command: str, **kwargs: Any) -> str:
            run.log_protocol("outbound", "scpi_tcp", f"SCPI: {command}", session_alias=self._session_alias)
            response = original_query(command, **kwargs)
            run.log_protocol(
                "inbound", "scpi_tcp", f"SCPI response to {command!r}: {response!r}",
                session_alias=self._session_alias,
            )
            return response

        client.query = _traced_query  # type: ignore[method-assign]

        original_get_text = client.http.get_text

        def _traced_get_text(path: str) -> str:
            run.log_protocol("outbound", "http", f"HTTP GET {path}", session_alias=self._session_alias)
            response = original_get_text(path)
            run.log_protocol(
                "inbound", "http", f"HTTP response to GET {path}: {response[:200]!r}",
                session_alias=self._session_alias,
            )
            return response

        client.http.get_text = _traced_get_text  # type: ignore[method-assign]

    def _end_suite(self, name: str, attributes: dict[str, Any]) -> None:
        """Robot listener hook providing a final safety net for suite teardown."""
        self.disconnect()

    def _device(self) -> EResistorClient:
        if self._client is None:
            raise RuntimeError("E-Resistor is not connected. Call 'Connect To EResistor' first.")
        return self._client

    @keyword("Connect To EResistor")
    @_evidenced
    def connect(self, host: str | None = None, all_off_on_connect: bool = False) -> str:
        """Connect and return the device ``*IDN?`` response.

        ``all_off_on_connect`` provides an explicit safe-start option.
        """
        if self._client is not None:
            self.disconnect()
        if self._profile:
            self._client = EResistorClient.from_profile(load_profile(self._profile))
        else:
            settings = dict(self._settings)
            if host is not None:
                settings["host"] = str(host)
            self._client = EResistorClient(**settings)
        self._trace_client_protocol(self._client)
        self._client.safe_connect(all_off_on_connect=_bool(all_off_on_connect))
        identity = self._client.idn()
        logger.info(f"Connected to E-Resistor: {identity}")
        if self._evidence is not None:
            self._evidence.record_device_identity(
                manufacturer="OpenBench",
                device_family="E-Resistor programmable resistor matrix",
                identity=identity,
                host=self._client.host,
                scpi_port=self._client.scpi_port,
                serial=_evidence._safe_call(self._client, "get_serial"),
                firmware_version=_evidence._safe_call(self._client, "get_firmware_version"),
            )
        return identity

    @keyword("Disconnect From EResistor")
    @_evidenced
    def disconnect(self, all_off: bool = True) -> None:
        """Safely disconnect. By default all outputs are opened first."""
        if self._client is None:
            return
        client, self._client = self._client, None
        if not _bool(all_off):
            client.shutdown_policy = type(client.shutdown_policy).LEAVE_AS_IS
        client.close()

    @keyword("E-Resistor Should Be Connected")
    @_evidenced
    def should_be_connected(self) -> None:
        state = self._device().connection_state.value
        if state != "CONNECTED":
            raise AssertionError(f"Expected CONNECTED state, got {state}")

    # ------------------------------------------------------------------
    # RFDS-002 mandatory universal keywords
    #
    # Thin, idempotent wrappers over the device-specific keywords above, kept
    # for generic/cross-driver tooling that expects the RFDS canonical names.
    # This driver supports a single connection, so ``alias`` is accepted for
    # interface compatibility but otherwise unused.
    # ------------------------------------------------------------------
    _PUBLIC_STATE = {
        "DISCONNECTED": "disconnected",
        "CONNECTED": "connected",
        "RECONNECTING": "recovering",
        "LOST": "faulted",
        "CLOSED": "disconnected",
    }

    def _connection_state(self) -> dict[str, Any]:
        """Build the RFDS-002 Section 12.1 normalized connection-state dictionary."""
        client = self._client
        if client is None:
            return {
                "alias": "default", "resource": None, "connected": False,
                "communication_ok": False, "transport": None, "identity": None,
                "timeout_s": self._settings.get("timeout"), "state": "disconnected",
            }
        state_value = client.connection_state.value
        identity_str: str | None = None
        if state_value == "CONNECTED":
            try:
                identity_str = client.idn()
            except Exception:
                identity_str = None
        return {
            "alias": "default",
            "resource": client.host,
            "connected": state_value == "CONNECTED",
            "communication_ok": identity_str is not None,
            "transport": "scpi_tcp",
            "identity": identity_str,
            "timeout_s": self._settings.get("timeout"),
            "state": self._PUBLIC_STATE.get(state_value, "faulted"),
        }

    @keyword("Connect")
    @_evidenced
    def generic_connect(
        self,
        resource: str | None = None,
        alias: str = "default",
        timeout_s: float | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """RFDS-002 generic connect. ``resource`` is the host/IP (see ``Connect To EResistor``).

        Idempotent when already connected to the same ``resource``.
        """
        del alias
        if self._client is not None and self._client.connection_state.value == "CONNECTED":
            if resource and str(self._client.host) != str(resource):
                raise RuntimeError(
                    f"Already connected to {self._client.host!r}; disconnect before connecting to {resource!r}."
                )
            return self._connection_state()
        if timeout_s is not None and not self._profile:
            self._settings["timeout"] = float(timeout_s)
        all_off_on_connect = options.pop("all_off_on_connect", False)
        self.connect(host=resource, all_off_on_connect=all_off_on_connect)
        return self._connection_state()

    @keyword("Disconnect")
    @_evidenced
    def generic_disconnect(self, alias: str | None = None) -> None:
        """RFDS-002 generic disconnect. Idempotent: succeeds even if already disconnected."""
        del alias
        self.disconnect()

    @keyword("Is Connected")
    @_evidenced
    def is_connected(self, alias: str | None = None) -> bool:
        """Return whether the driver is connected."""
        del alias
        return self._client is not None and self._client.connection_state.value == "CONNECTED"

    @keyword("Get Connection State")
    @_evidenced
    def get_connection_state(self, alias: str | None = None, refresh: bool = False) -> dict[str, Any]:
        """Return the RFDS-002 Section 12.1 normalized connection-state dictionary."""
        del alias
        if _bool(refresh) and self._client is not None:
            try:
                self._client.ping()
            except Exception:
                pass
        return self._connection_state()

    @keyword("Check Communication")
    @_evidenced
    def check_communication(self, alias: str | None = None) -> bool:
        """Perform a bounded, non-destructive communication check. Raises on failure."""
        del alias
        self._device().idn()
        return True

    @keyword("Get Identity")
    @_evidenced
    def get_identity_generic(self, alias: str | None = None, refresh: bool = True) -> str:
        """Return a stable human-readable identity string."""
        del alias, refresh
        return self._device().idn()

    @keyword("Get EResistor Identity")
    @_evidenced
    def get_identity(self) -> str:
        return self._device().idn()

    @keyword("Ping EResistor")
    @_evidenced
    def ping(self) -> bool:
        return self._device().ping()

    @keyword("Identify EResistor")
    @_evidenced
    def identify(self, duration_s: float = 5.0) -> str:
        return self._device().identify(float(duration_s))

    @keyword("Get EResistor Information")
    @_evidenced
    def get_information(self) -> dict[str, Any]:
        dev = self._device()
        return {"identity": dev.idn(), "serial": dev.get_serial(),
                "firmware_version": dev.get_firmware_version(),
                "connection_state": dev.connection_state.value,
                "host": dev.host, "scpi_port": dev.scpi_port}

    @keyword("Send EResistor SCPI Query")
    @_evidenced
    def query(self, command: str, multiline_until: str | None = None) -> str:
        """Send an advanced/raw SCPI request and return its response."""
        return self._device().query(command, multiline_until=multiline_until)

    @keyword("Get EResistor Status")
    @_evidenced
    def get_status(self) -> dict[str, str]:
        return self._device().get_status()

    @keyword("Get EResistor Error")
    @_evidenced
    def get_error(self) -> str:
        return self._device().get_error()

    @keyword("Clear EResistor Errors")
    @_evidenced
    def clear_errors(self) -> str:
        return self._device().clear_errors()

    @keyword("Set EResistor Mask")
    @_evidenced
    def set_mask(self, channel: int, mask: int | str, force: bool = False) -> str:
        return self._device().set_mask(int(channel), mask, force=_bool(force))

    @keyword("Get EResistor Mask")
    @_evidenced
    def get_mask(self, channel: int) -> str:
        return self._device().get_mask(int(channel))

    @keyword("Get All EResistor Masks")
    @_evidenced
    def get_all_masks(self) -> dict[str, str]:
        return _robot_value(self._device().get_all_masks())

    @keyword("Set All EResistor Masks")
    @_evidenced
    def set_all_masks(self, *masks: Any, force: bool = False) -> dict[str, str]:
        """Set exactly eight masks, passed as eight scalar arguments or one list."""
        values = list(masks[0]) if len(masks) == 1 and isinstance(masks[0], (list, tuple)) else list(masks)
        return _robot_value(self._device().set_all_masks(values, force=_bool(force)))

    @keyword("Set Selected EResistor Masks")
    @_evidenced
    def set_selected_masks(self, masks: Mapping[Any, Any], force: bool = False) -> dict[str, str]:
        values = {int(k): v for k, v in masks.items()}
        return _robot_value(self._device().set_masks(values, force=_bool(force)))

    @keyword("Open All EResistor Channels")
    @_evidenced
    def all_off(self) -> str:
        return self._device().all_off()

    @keyword("EResistor Mask Should Be")
    @_evidenced
    def mask_should_be(self, channel: int, expected: int | str) -> None:
        actual = self.get_mask(channel)
        wanted = normalize_mask(expected)
        if actual != wanted:
            raise AssertionError(f"CH{channel} mask is {actual}, expected {wanted}")

    @keyword("Download EResistor Calibration")
    @_evidenced
    def download_calibration(self) -> dict[str, Any]:
        return _robot_value(self._device().download_calibration())

    @keyword("Download EResistor Channel Calibration")
    @_evidenced
    def download_channel_calibration(self, channel: int) -> dict[str, Any]:
        return _robot_value(self._device().download_channel_calibration(int(channel)))

    @keyword("Load EResistor Calibration")
    @_evidenced
    def load_calibration(self, path: str) -> dict[str, Any]:
        return _robot_value(self._device().load_calibration(path))

    @keyword("Save EResistor Calibration")
    @_evidenced
    def save_calibration(self, path: str) -> None:
        self._device().save_calibration(path)

    @keyword("Build EResistor Resistance Cache")
    @_evidenced
    def build_resistance_cache(self) -> None:
        self._device().build_resistance_cache()

    @keyword("Calculate EResistor Resistance")
    @_evidenced
    def resistance_for_mask(self, channel: int, mask: int | str) -> float:
        return self._device().get_resistance_for_mask(int(channel), mask)

    @keyword("Find Closest EResistor Resistance")
    @_evidenced
    def find_closest_resistance(self, channel: int, resistance_ohm: float,
                                allow_closest_out_of_range: bool = False) -> dict[str, Any]:
        result = self._device().find_closest_resistance(
            int(channel), float(resistance_ohm),
            allow_closest_out_of_range=_bool(allow_closest_out_of_range))
        return _robot_value(result)

    @keyword("Set EResistor Resistance")
    @_evidenced
    def set_resistance(self, channel: int, resistance_ohm: float,
                       allow_closest_out_of_range: bool = False, force: bool = False) -> dict[str, Any]:
        return _robot_value(self._device().set_resistance(
            int(channel), float(resistance_ohm),
            allow_closest_out_of_range=_bool(allow_closest_out_of_range), force=_bool(force)))

    @keyword("Set Multiple EResistor Resistances")
    @_evidenced
    def set_resistances(self, values: Mapping[Any, Any] | Sequence[Any],
                        atomic: bool = True, force: bool = False) -> list[dict[str, Any]]:
        normalized = ({int(k): float(v) for k, v in values.items()} if isinstance(values, Mapping)
                      else [None if v is None else float(v) for v in values])
        return _robot_value(self._device().set_resistances(
            normalized, atomic=_bool(atomic), force=_bool(force)))

    @keyword("Load EResistor Temperature Table")
    @_evidenced
    def load_temperature_table(self, channel: int, path: str) -> dict[str, Any]:
        table = self._device().load_temperature_table(int(channel), path)
        return {"source": table.source, "minimum_temperature_c": table.min_temperature_c,
                "maximum_temperature_c": table.max_temperature_c}

    @keyword("Load EResistor Temperature Table For All Channels")
    @_evidenced
    def load_temperature_table_for_all(self, path: str) -> dict[str, Any]:
        table = self._device().load_temperature_table_for_all(path)
        return {"source": table.source, "minimum_temperature_c": table.min_temperature_c,
                "maximum_temperature_c": table.max_temperature_c}

    @keyword("Set EResistor Temperature")
    @_evidenced
    def set_temperature(self, channel: int, temperature_c: float, interpolation: str = "linear",
                        allow_extrapolation: bool = False, force: bool = False) -> dict[str, Any]:
        return _robot_value(self._device().set_temperature(
            int(channel), float(temperature_c), interpolation=interpolation,
            allow_extrapolation=_bool(allow_extrapolation), force=_bool(force)))

    @keyword("Start EResistor Watchdog")
    @_evidenced
    def start_watchdog(self) -> None:
        self._device().start_watchdog()

    @keyword("Stop EResistor Watchdog")
    @_evidenced
    def stop_watchdog(self) -> None:
        self._device().stop_watchdog()

    @keyword("Get EResistor Metrics")
    @_evidenced
    def get_metrics(self) -> dict[str, Any]:
        return _robot_value(self._device().metrics.snapshot())

    @keyword("Discover EResistor Boards")
    @_evidenced
    def discover(self, subnet: str, timeout: float = 0.25, max_workers: int = 64) -> list[dict[str, Any]]:
        return [board.as_dict() for board in discover_boards(
            subnet, timeout=float(timeout), max_workers=int(max_workers))]

    @keyword("Auto Discover EResistor Boards")
    @_evidenced
    def discover_auto(self, timeout: float = 0.25, max_workers: int = 64) -> list[dict[str, Any]]:
        return [board.as_dict() for board in discover_boards_auto(
            timeout=float(timeout), max_workers=int(max_workers))]

    @keyword("Export Diagnostic Bundle")
    @_evidenced
    def export_diagnostic_bundle(self, destination: str | None = None) -> str | None:
        """Zip this session's RFDS-008 evidence run to ``destination`` for troubleshooting.

        Works whether or not the board is currently connected, and does not
        finalize the run — ``Disconnect From EResistor`` remains the point at
        which ``run_summary.json``/``evidence_manifest.json`` are written for
        the last time. Returns the archive path, or ``None`` if
        ``evidence_enabled=${FALSE}`` was passed to this library instance.
        """
        run = self._ensure_evidence()
        return run.export_diagnostic_bundle(None if destination in (None, "") else str(destination))
