"""Curve-profile parsing and simulation runtime."""
from __future__ import annotations

import csv
import io
import json
import logging
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Literal

from .exceptions import SimulationError
from .models import SimulationLogEntry

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurvePoint:
    time_s: float
    value: float
    value_type: str  # "resistance" or "temperature"


class CurveProfile:
    """A time-ordered curve profile.

    Supported CSV formats:
    - time_s,resistance_ohm
    - time_s,temperature_c
    - temperature_c,dwell_s
    - resistance_ohm,dwell_s
    - value_type,value,dwell_s
    """

    def __init__(self, points: Iterable[CurvePoint], *, source: str | None = None) -> None:
        self.points = sorted(list(points), key=lambda p: p.time_s)
        self.source = source
        self._validate()

    @classmethod
    def from_csv(cls, path: str | Path, *, input_type: str | None = None) -> "CurveProfile":
        return cls.from_csv_text(Path(path).read_text(encoding="utf-8-sig"), input_type=input_type, source=str(path))

    @classmethod
    def from_csv_text(cls, text: str, *, input_type: str | None = None, source: str | None = None) -> "CurveProfile":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise SimulationError("Curve CSV has no header")
        fields = {f.strip().lower(): f for f in reader.fieldnames}

        def has(name: str) -> bool:
            return name in fields

        points: list[CurvePoint] = []
        # Absolute time formats.
        if has("time_s") and (has("resistance_ohm") or has("resistance") or has("temperature_c") or has("temperature")):
            if has("resistance_ohm") or has("resistance"):
                value_col = fields.get("resistance_ohm") or fields["resistance"]
                value_type = "resistance"
            else:
                value_col = fields.get("temperature_c") or fields["temperature"]
                value_type = "temperature"
            for row in reader:
                points.append(CurvePoint(float(row[fields["time_s"]]), float(row[value_col]), value_type))
            return cls(points, source=source)

        # Dwell format with explicit value_type.
        if has("value_type") and has("value") and has("dwell_s"):
            t = 0.0
            for row in reader:
                vt = str(row[fields["value_type"]]).strip().lower()
                if vt in {"temperature_c", "temperature", "temp_c", "temp"}:
                    vt = "temperature"
                elif vt in {"resistance_ohm", "resistance", "ohm", "r"}:
                    vt = "resistance"
                else:
                    raise SimulationError(f"Unsupported curve value_type: {vt!r}")
                points.append(CurvePoint(t, float(row[fields["value"]]), vt))
                t += float(row[fields["dwell_s"]])
            return cls(points, source=source)

        # Dwell format with implicit type from column.
        if has("dwell_s") and (has("temperature_c") or has("temperature") or has("resistance_ohm") or has("resistance")):
            t = 0.0
            if has("temperature_c") or has("temperature"):
                col = fields.get("temperature_c") or fields["temperature"]
                vt = "temperature"
            else:
                col = fields.get("resistance_ohm") or fields["resistance"]
                vt = "resistance"
            for row in reader:
                points.append(CurvePoint(t, float(row[col]), vt))
                t += float(row[fields["dwell_s"]])
            return cls(points, source=source)

        raise SimulationError("Unsupported curve CSV format")

    def _validate(self) -> None:
        if not self.points:
            raise SimulationError("Curve profile contains no points")
        last = -float("inf")
        for p in self.points:
            if p.time_s < 0:
                raise SimulationError("Curve time values must be >= 0")
            if p.time_s < last:
                raise SimulationError("Curve points must be sorted by time")
            if p.value_type not in {"resistance", "temperature"}:
                raise SimulationError(f"Unsupported point value_type {p.value_type!r}")
            last = p.time_s


class CurveSimulation:
    """Blocking/background simulation runner.

    The runner delegates actual output setting to a callback supplied by the
    client. It supports stop, pause, repeat count, drift correction, and log
    export. The callback must return a SetResistanceResult-like object with
    calculated_ohm, error_percent, and mask attributes.
    """

    def __init__(
        self,
        profile: CurveProfile,
        *,
        channel: int,
        apply_callback: Callable[[int, str, float], object],
        repeat: int | None = 1,
        on_error: str = "stop_and_all_off",
        max_total_duration_s: float | None = None,
        state_file: str | None = None,
        all_off_callback: Callable[[], None] | None = None,
    ) -> None:
        if repeat is not None and repeat < 1:
            raise SimulationError("repeat must be >=1 or None for infinite")
        self.profile = profile
        self.channel = channel
        self.apply_callback = apply_callback
        self.repeat = repeat
        self.on_error = on_error
        self.max_total_duration_s = max_total_duration_s
        self.state_file = state_file
        self.all_off_callback = all_off_callback
        self.log: list[SimulationLogEntry] = []
        self._stop = threading.Event()
        self._pause = threading.Event()
        self._pause.set()
        self._thread: threading.Thread | None = None
        self._started_at: float | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            raise SimulationError("Simulation already running")
        self._thread = threading.Thread(target=self.run, name=f"EResistorCurveCH{self.channel}", daemon=True)
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        if self._thread:
            self._thread.join(timeout)

    def stop(self) -> None:
        self._stop.set()

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    def run(self) -> None:
        self._started_at = time.monotonic()
        repeat_count = 0
        while not self._stop.is_set() and (self.repeat is None or repeat_count < self.repeat):
            cycle_start = time.monotonic()
            for idx, point in enumerate(self.profile.points):
                if self._stop.is_set():
                    break
                self._pause.wait()
                if self.max_total_duration_s is not None and self._started_at is not None:
                    if time.monotonic() - self._started_at > self.max_total_duration_s:
                        raise SimulationError("Simulation exceeded max_total_duration_s")
                target_time = cycle_start + point.time_s
                # Drift correction: sleep until cumulative expected time, not just per-step delta.
                while not self._stop.is_set():
                    remaining = target_time - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(remaining, 0.1))
                if self._stop.is_set():
                    break
                try:
                    result = self.apply_callback(self.channel, point.value_type, point.value)
                    elapsed = time.monotonic() - cycle_start
                    timing_error = elapsed - point.time_s
                    entry = SimulationLogEntry(
                        timestamp=datetime.now(timezone.utc),
                        elapsed_s=elapsed,
                        channel=self.channel,
                        requested_type=point.value_type,
                        requested_value=point.value,
                        requested_resistance_ohm=getattr(result, "requested_ohm", point.value),
                        calculated_resistance_ohm=getattr(result, "calculated_ohm", float("nan")),
                        error_percent=getattr(result, "error_percent", float("nan")),
                        mask=getattr(result, "mask", "????"),
                        timing_error_s=timing_error,
                    )
                    self.log.append(entry)
                    self._persist_state(repeat_count, idx)
                except Exception as exc:  # noqa: BLE001 - converted based on configured policy
                    _LOG.exception("Simulation point failed")
                    if self.on_error in {"retry", "retry_once"}:
                        try:
                            self.apply_callback(self.channel, point.value_type, point.value)
                            continue
                        except Exception:
                            pass
                    if self.on_error in {"all_off_and_stop", "stop_and_all_off"} and self.all_off_callback:
                        self.all_off_callback()
                    if self.on_error in {"skip_and_continue", "skip"}:
                        continue
                    raise SimulationError(f"Simulation failed at point {idx}: {exc}") from exc
            repeat_count += 1

    def _persist_state(self, repeat_index: int, point_index: int) -> None:
        if not self.state_file:
            return
        payload = {
            "channel": self.channel,
            "repeat_index": repeat_index,
            "point_index": point_index,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": self.profile.source,
        }
        Path(self.state_file).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def export_log_csv(self, path: str | Path) -> None:
        with Path(path).open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(self.log[0]).keys()) if self.log else [
                "timestamp", "elapsed_s", "channel", "requested_type", "requested_value",
                "requested_resistance_ohm", "calculated_resistance_ohm", "error_percent", "mask",
                "timing_error_s",
            ])
            writer.writeheader()
            for entry in self.log:
                row = asdict(entry)
                row["timestamp"] = entry.timestamp.isoformat()
                writer.writerow(row)

    def export_log_json(self, path: str | Path) -> None:
        payload = []
        for entry in self.log:
            row = asdict(entry)
            row["timestamp"] = entry.timestamp.isoformat()
            payload.append(row)
        Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
