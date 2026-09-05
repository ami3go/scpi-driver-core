"""Temperature-to-resistance table support."""
from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .exceptions import TemperatureTableError

_TEMP_ALIASES = {"temperature_c", "temp_c", "temperature", "temp", "t"}
_RES_ALIASES = {"resistance_ohm", "res_ohm", "resistance", "ohm", "r"}


@dataclass(frozen=True)
class TemperaturePoint:
    temperature_c: float
    resistance_ohm: float


class TemperatureTable:
    def __init__(self, points: Iterable[TemperaturePoint], *, source: str | None = None) -> None:
        self.points = sorted(list(points), key=lambda p: p.temperature_c)
        self.source = source
        self._validate()

    @classmethod
    def from_csv(cls, path: str | Path) -> "TemperatureTable":
        text = Path(path).read_text(encoding="utf-8-sig")
        return cls.from_csv_text(text, source=str(path))

    @classmethod
    def from_csv_text(cls, text: str, *, source: str | None = None) -> "TemperatureTable":
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise TemperatureTableError("Temperature CSV has no header")
        fields = {f.strip().lower(): f for f in reader.fieldnames}

        def find(aliases: set[str], label: str) -> str:
            for alias in aliases:
                if alias in fields:
                    return fields[alias]
            raise TemperatureTableError(f"Missing {label} column; accepted aliases: {sorted(aliases)}")

        temp_col = find(_TEMP_ALIASES, "temperature")
        res_col = find(_RES_ALIASES, "resistance")
        points: list[TemperaturePoint] = []
        for row in reader:
            if not row:
                continue
            try:
                t = float(str(row[temp_col]).strip())
                r = float(str(row[res_col]).strip())
            except (ValueError, TypeError) as exc:
                raise TemperatureTableError(f"Invalid temperature table row: {row}") from exc
            points.append(TemperaturePoint(t, r))
        return cls(points, source=source)

    def _validate(self) -> None:
        if len(self.points) < 2:
            raise TemperatureTableError("Temperature table must contain at least two points")
        temps = [p.temperature_c for p in self.points]
        if len(set(temps)) != len(temps):
            raise TemperatureTableError("Temperature values must be unique")
        for p in self.points:
            if not math.isfinite(p.temperature_c):
                raise TemperatureTableError("Temperature values must be finite")
            if not math.isfinite(p.resistance_ohm) or p.resistance_ohm <= 0:
                raise TemperatureTableError("Resistance values must be positive finite values")

    @property
    def min_temperature_c(self) -> float:
        return self.points[0].temperature_c

    @property
    def max_temperature_c(self) -> float:
        return self.points[-1].temperature_c

    def resistance_at(
        self,
        temperature_c: float,
        *,
        mode: str = "linear",
        allow_extrapolation: bool = False,
    ) -> float:
        if not math.isfinite(temperature_c):
            raise TemperatureTableError("Temperature must be finite")
        if not allow_extrapolation and not (self.min_temperature_c <= temperature_c <= self.max_temperature_c):
            raise TemperatureTableError(
                f"Temperature {temperature_c:g} °C outside table range "
                f"{self.min_temperature_c:g}..{self.max_temperature_c:g} °C"
            )
        pts = self.points
        if temperature_c <= pts[0].temperature_c:
            p0, p1 = pts[0], pts[1]
        elif temperature_c >= pts[-1].temperature_c:
            p0, p1 = pts[-2], pts[-1]
        else:
            p0, p1 = pts[0], pts[1]
            for i in range(len(pts) - 1):
                if pts[i].temperature_c <= temperature_c <= pts[i + 1].temperature_c:
                    p0, p1 = pts[i], pts[i + 1]
                    break
        span = p1.temperature_c - p0.temperature_c
        if span == 0:
            raise TemperatureTableError("Duplicate temperature points in table")
        frac = (temperature_c - p0.temperature_c) / span
        if mode == "linear":
            return p0.resistance_ohm + frac * (p1.resistance_ohm - p0.resistance_ohm)
        if mode == "log_resistance":
            log_r0 = math.log(p0.resistance_ohm)
            log_r1 = math.log(p1.resistance_ohm)
            return math.exp(log_r0 + frac * (log_r1 - log_r0))
        raise TemperatureTableError(f"Unsupported interpolation mode: {mode!r}")
