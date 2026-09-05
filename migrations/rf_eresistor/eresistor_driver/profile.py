"""Device profile load/save helpers."""
from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar, get_origin, get_args

from .models import (
    CalibrationConfig,
    ConnectionLossPolicy,
    DeviceProfile,
    LoggingConfig,
    ReconnectConfig,
    ReconnectStatePolicy,
    SafetyConfig,
    ShutdownPolicy,
    WatchdogConfig,
)


def _serialize(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _serialize(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _load_yaml_or_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Loading YAML profiles requires PyYAML: pip install eresistor-driver[yaml]") from exc
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ValueError("Profile YAML root must be a mapping")
        return data
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Profile JSON root must be a mapping")
    return data


def _save_yaml_or_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Saving YAML profiles requires PyYAML: pip install eresistor-driver[yaml]") from exc
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    else:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _enum(enum_cls, value):
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)


def profile_from_dict(data: dict[str, Any]) -> DeviceProfile:
    safety_data = data.get("safety", {}) or {}
    reconnect_data = data.get("reconnect", {}) or {}
    watchdog_data = data.get("watchdog", {}) or {}
    calibration_data = data.get("calibration", {}) or {}
    logging_data = data.get("logging", {}) or {}

    if "connection_loss_policy" in safety_data:
        safety_data["connection_loss_policy"] = _enum(ConnectionLossPolicy, safety_data["connection_loss_policy"])
    if "state_policy" in reconnect_data:
        reconnect_data["state_policy"] = _enum(ReconnectStatePolicy, reconnect_data["state_policy"])

    return DeviceProfile(
        device_name=data.get("device_name"),
        host=data.get("host", "192.168.7.50"),
        scpi_port=int(data.get("scpi_port", 5025)),
        http_port=int(data.get("http_port", 80)),
        serial=data.get("serial"),
        default_timeout_s=float(data.get("default_timeout_s", 2.0)),
        min_firmware_version=data.get("min_firmware_version"),
        firmware_check_on_connect=bool(data.get("firmware_check_on_connect", False)),
        safety=SafetyConfig(**safety_data),
        reconnect=ReconnectConfig(**reconnect_data),
        watchdog=WatchdogConfig(**watchdog_data),
        calibration=CalibrationConfig(**calibration_data),
        logging=LoggingConfig(**logging_data),
        temperature_tables=dict(data.get("temperature_tables", {}) or {}),
        state_persistence_file=data.get("state_persistence_file"),
        shutdown_policy=_enum(ShutdownPolicy, data.get("shutdown_policy", ShutdownPolicy.ALL_OFF.value)),
    )


def profile_to_dict(profile: DeviceProfile) -> dict[str, Any]:
    return _serialize(profile)


def load_profile(path: str | Path) -> DeviceProfile:
    return profile_from_dict(_load_yaml_or_json(Path(path)))


def save_profile(profile: DeviceProfile, path: str | Path) -> None:
    _save_yaml_or_json(Path(path), profile_to_dict(profile))


DeviceProfile.load = staticmethod(load_profile)  # type: ignore[attr-defined]
DeviceProfile.save = lambda self, path: save_profile(self, path)  # type: ignore[attr-defined]
