"""Calibration parsing, validation, and JSON persistence."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .exceptions import CalibrationError
from .models import BranchCalibration, ChannelCalibration, DeviceCalibration
from .validation import CHANNEL_COUNT

_RES_SUFFIX_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*([RrKkMm]?)\s*(?:ohm|ohms|Ω)?\s*$")


def parse_resistance_value(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        text = str(value).strip()
        match = _RES_SUFFIX_RE.match(text)
        if not match:
            raise CalibrationError(f"Invalid resistance value: {value!r}")
        result = float(match.group(1))
        suffix = match.group(2).upper()
        if suffix == "K":
            result *= 1_000.0
        elif suffix == "M":
            result *= 1_000_000.0
    if not math.isfinite(result) or result <= 0:
        raise CalibrationError(f"Resistance must be positive finite value, got {value!r}")
    return result


def parse_compact_calibration(text: str, *, source: str = "scpi_compact") -> DeviceCalibration:
    """Parse compact SCPI format: CH1:0,Q16,626;...|CH2:..."""
    channels: dict[int, ChannelCalibration] = {}
    sections = [s.strip() for s in text.strip().split("|") if s.strip()]
    for section in sections:
        if ":" not in section:
            continue
        head, body = section.split(":", 1)
        m = re.search(r"CH(?:AN(?:NEL)?)?\s*(\d+)", head, re.IGNORECASE)
        if not m:
            continue
        channel = int(m.group(1))
        branches: list[BranchCalibration] = []
        for record in [r.strip() for r in body.split(";") if r.strip()]:
            parts = [p.strip() for p in record.split(",")]
            if len(parts) < 3:
                continue
            branches.append(
                BranchCalibration(
                    bit_index=int(parts[0]),
                    mosfet_name=parts[1],
                    resistance_ohm=parse_resistance_value(parts[2]),
                )
            )
        channels[channel] = ChannelCalibration(channel=channel, branches=branches, source=source)
    cal = DeviceCalibration(channels=channels, source=source)
    validate_device_calibration(cal)
    cal.checksum = calibration_checksum(cal)
    return cal


def _parse_csv_rows(text: str) -> list[BranchCalibration]:
    # Drop firmware markers/comments, then parse CSV.
    filtered: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        filtered.append(line)
    if not filtered:
        raise CalibrationError("Calibration CSV block is empty")
    reader = csv.DictReader(io.StringIO("\n".join(filtered)))
    if not reader.fieldnames:
        raise CalibrationError("Calibration CSV has no header")
    field_map = {name.strip().lower(): name for name in reader.fieldnames}

    def field(*names: str) -> str:
        for name in names:
            if name.lower() in field_map:
                return field_map[name.lower()]
        raise CalibrationError(f"Missing required column; expected one of {names}")

    bit_col = field("bit", "bit_index", "index")
    name_col = field("mosfet_name", "mosfet", "branch", "name")
    res_col = field("nominal_resistance", "resistance_ohm", "resistance", "ohm", "r")
    branches: list[BranchCalibration] = []
    for row in reader:
        if not row:
            continue
        branches.append(
            BranchCalibration(
                bit_index=int(str(row[bit_col]).strip()),
                mosfet_name=str(row[name_col]).strip(),
                resistance_ohm=parse_resistance_value(row[res_col]),
            )
        )
    return branches


def parse_begin_end_calibration(text: str, *, source: str = "scpi_file") -> DeviceCalibration:
    """Parse one or more #BEGIN CHn ... #END CHn calibration blocks."""
    channels: dict[int, ChannelCalibration] = {}
    current_channel: int | None = None
    current_lines: list[str] = []

    def finish() -> None:
        nonlocal current_channel, current_lines
        if current_channel is None:
            return
        branches = _parse_csv_rows("\n".join(current_lines))
        channels[current_channel] = ChannelCalibration(current_channel, branches, source=source)
        current_channel = None
        current_lines = []

    for line in text.splitlines():
        stripped = line.strip()
        begin = re.match(r"#BEGIN\s+CH\s*(\d+)", stripped, re.IGNORECASE)
        end = re.match(r"#END\s+(?:CH\s*(\d+)|ALL)", stripped, re.IGNORECASE)
        if begin:
            finish()
            current_channel = int(begin.group(1))
            current_lines = []
            continue
        if end:
            finish()
            continue
        if current_channel is not None:
            current_lines.append(line)
    finish()

    if not channels:
        # Some HTTP endpoints may return plain CSV for one channel. Assume CH1; caller can remap.
        branches = _parse_csv_rows(text)
        channels[1] = ChannelCalibration(1, branches, source=source)
    cal = DeviceCalibration(channels=channels, source=source)
    validate_device_calibration(cal, require_all_channels=False)
    cal.checksum = calibration_checksum(cal)
    return cal


def merge_calibrations(calibrations: Iterable[DeviceCalibration], *, source: str = "merged") -> DeviceCalibration:
    channels: dict[int, ChannelCalibration] = {}
    for cal in calibrations:
        channels.update(cal.channels)
    merged = DeviceCalibration(channels=channels, source=source)
    validate_device_calibration(merged, require_all_channels=False)
    merged.checksum = calibration_checksum(merged)
    return merged


def validate_channel_calibration(cal: ChannelCalibration) -> None:
    if cal.channel < 1 or cal.channel > CHANNEL_COUNT:
        raise CalibrationError(f"Invalid channel number in calibration: {cal.channel}")
    if len(cal.branches) != 16:
        raise CalibrationError(f"CH{cal.channel} calibration must contain 16 branches, got {len(cal.branches)}")
    bits = [b.bit_index for b in cal.branches]
    if sorted(bits) != list(range(16)):
        raise CalibrationError(f"CH{cal.channel} branch bits must be exactly 0..15, got {sorted(bits)}")
    for b in cal.branches:
        if not b.mosfet_name:
            raise CalibrationError(f"CH{cal.channel} bit {b.bit_index} has empty MOSFET name")
        if not math.isfinite(b.resistance_ohm) or b.resistance_ohm <= 0:
            raise CalibrationError(f"CH{cal.channel} bit {b.bit_index} invalid resistance {b.resistance_ohm}")


def validate_device_calibration(cal: DeviceCalibration, *, require_all_channels: bool = False) -> None:
    if not cal.channels:
        raise CalibrationError("Calibration contains no channels")
    if require_all_channels and sorted(cal.channels) != list(range(1, CHANNEL_COUNT + 1)):
        raise CalibrationError(f"Calibration must contain channels 1..{CHANNEL_COUNT}, got {sorted(cal.channels)}")
    for channel, ch_cal in cal.channels.items():
        if channel != ch_cal.channel:
            raise CalibrationError(f"Calibration map key {channel} does not match channel {ch_cal.channel}")
        validate_channel_calibration(ch_cal)


def calibration_checksum(cal: DeviceCalibration) -> str:
    payload: list[tuple[int, int, str, float]] = []
    for channel in sorted(cal.channels):
        ch = cal.channels[channel]
        for b in sorted(ch.branches, key=lambda x: x.bit_index):
            payload.append((channel, b.bit_index, b.mosfet_name, round(b.resistance_ohm, 12)))
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def calibration_to_dict(cal: DeviceCalibration) -> dict:
    return {
        "serial": cal.serial,
        "firmware_version": cal.firmware_version,
        "downloaded_at": cal.downloaded_at.isoformat() if cal.downloaded_at else None,
        "source": cal.source,
        "checksum": cal.checksum or calibration_checksum(cal),
        "channels": {
            str(ch): {
                "source": ch_cal.source,
                "branches": [asdict(b) for b in sorted(ch_cal.branches, key=lambda x: x.bit_index)],
            }
            for ch, ch_cal in sorted(cal.channels.items())
        },
    }


def calibration_from_dict(data: dict) -> DeviceCalibration:
    channels: dict[int, ChannelCalibration] = {}
    for ch_text, ch_data in data.get("channels", {}).items():
        ch = int(ch_text)
        branches = [BranchCalibration(**b) for b in ch_data["branches"]]
        channels[ch] = ChannelCalibration(ch, branches, source=ch_data.get("source", data.get("source", "local_json")))
    downloaded_at = data.get("downloaded_at")
    cal = DeviceCalibration(
        channels=channels,
        serial=data.get("serial"),
        firmware_version=data.get("firmware_version"),
        downloaded_at=datetime.fromisoformat(downloaded_at) if downloaded_at else None,
        source=data.get("source", "local_json"),
        checksum=data.get("checksum"),
    )
    validate_device_calibration(cal, require_all_channels=False)
    actual = calibration_checksum(cal)
    if cal.checksum and cal.checksum != actual:
        raise CalibrationError("Calibration checksum mismatch")
    cal.checksum = actual
    return cal


def save_calibration_json(cal: DeviceCalibration, path: str | Path) -> None:
    Path(path).write_text(json.dumps(calibration_to_dict(cal), indent=2), encoding="utf-8")


def load_calibration_json(path: str | Path) -> DeviceCalibration:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cal = calibration_from_dict(data)
    cal.source = "local_json"
    return cal


def calibration_age_hours(cal: DeviceCalibration) -> float | None:
    if cal.downloaded_at is None:
        return None
    dt = cal.downloaded_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
