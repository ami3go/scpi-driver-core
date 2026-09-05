"""PC-side equivalent-resistance calculation and closest-mask solver."""
from __future__ import annotations

import bisect
import math
import threading
from dataclasses import dataclass

from .exceptions import CalibrationError, ResistanceSolveError, SafetyLimitError
from .models import ChannelCalibration, DeviceCalibration, SafetyConfig, SetResistanceResult
from .validation import active_bits, count_active_bits, normalize_mask, validate_channel, mask_to_int


@dataclass(frozen=True)
class ResistanceCandidate:
    resistance_ohm: float
    mask_int: int
    active_count: int

    @property
    def mask(self) -> str:
        return f"{self.mask_int:04X}"


class ResistanceSolver:
    """Precomputing solver for one E-Resistor board calibration."""

    def __init__(self, calibration: DeviceCalibration, safety: SafetyConfig | None = None) -> None:
        self.calibration = calibration
        self.safety = safety or SafetyConfig()
        self._cache: dict[int, list[ResistanceCandidate]] = {}
        self._values: dict[int, list[float]] = {}
        self._lock = threading.RLock()

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()
            self._values.clear()

    def build_cache(self, channel: int | None = None) -> None:
        with self._lock:
            channels = [validate_channel(channel)] if channel is not None else sorted(self.calibration.channels)
            for ch in channels:
                self._cache[ch] = self._build_channel_cache(ch)
                self._values[ch] = [c.resistance_ohm for c in self._cache[ch]]

    def _channel_cal(self, channel: int) -> ChannelCalibration:
        channel = validate_channel(channel)
        try:
            return self.calibration.channels[channel]
        except KeyError as exc:
            raise CalibrationError(f"No calibration available for CH{channel}") from exc

    def _conductances(self, channel: int) -> list[float]:
        ch = self._channel_cal(channel)
        branches = ch.branch_by_bit()
        if sorted(branches) != list(range(16)):
            raise CalibrationError(f"CH{channel} calibration must contain branch bits 0..15")
        return [1.0 / branches[bit].resistance_ohm for bit in range(16)]

    def _build_channel_cache(self, channel: int) -> list[ResistanceCandidate]:
        g = self._conductances(channel)
        conductance = [0.0] * 65536
        candidates: list[ResistanceCandidate] = []
        for mask in range(1, 65536):
            low_bit = mask & -mask
            bit_index = low_bit.bit_length() - 1
            prev = mask ^ low_bit
            conductance[mask] = conductance[prev] + g[bit_index]
            resistance = 1.0 / conductance[mask]
            candidates.append(ResistanceCandidate(resistance, mask, mask.bit_count()))
        # Sort by resistance, then active count, then mask for deterministic tie-breaking.
        candidates.sort(key=lambda c: (c.resistance_ohm, c.active_count, c.mask_int))
        return candidates

    def equivalent_resistance(self, channel: int, mask: int | str) -> float:
        channel = validate_channel(channel)
        mask_i = mask_to_int(mask)
        if mask_i == 0:
            return math.inf
        g = self._conductances(channel)
        total_g = sum(g[bit] for bit in range(16) if mask_i & (1 << bit))
        if total_g <= 0:
            return math.inf
        return 1.0 / total_g

    def find_closest(
        self,
        channel: int,
        resistance_ohm: float,
        *,
        allow_closest_out_of_range: bool = False,
    ) -> SetResistanceResult:
        channel = validate_channel(channel)
        if math.isinf(resistance_ohm):
            return SetResistanceResult(channel, resistance_ohm, math.inf, math.nan, math.nan, "0000", [])
        if not math.isfinite(resistance_ohm) or resistance_ohm <= 0:
            raise ResistanceSolveError(f"Requested resistance must be positive finite value, got {resistance_ohm!r}")
        self._check_safety_requested(resistance_ohm)
        with self._lock:
            if channel not in self._cache:
                self.build_cache(channel)
            values = self._values[channel]
            cache = self._cache[channel]

            min_r = values[0]
            max_r = values[-1]
            if not allow_closest_out_of_range and (resistance_ohm < min_r or resistance_ohm > max_r):
                raise ResistanceSolveError(
                    f"Requested {resistance_ohm:g} Ω is outside achievable range for CH{channel}: "
                    f"{min_r:g}..{max_r:g} Ω"
                )

            pos = bisect.bisect_left(values, resistance_ohm)
            candidates: list[ResistanceCandidate] = []
            for idx in {pos - 2, pos - 1, pos, pos + 1, pos + 2}:
                if 0 <= idx < len(cache):
                    candidates.append(cache[idx])
            best = min(
                candidates,
                key=lambda c: (abs(c.resistance_ohm - resistance_ohm), c.active_count, c.mask_int),
            )
            self._check_safety_mask(best.mask)
            error = best.resistance_ohm - resistance_ohm
            error_percent = (error / resistance_ohm) * 100.0 if resistance_ohm else math.nan
            return SetResistanceResult(
                channel=channel,
                requested_ohm=float(resistance_ohm),
                calculated_ohm=best.resistance_ohm,
                error_ohm=error,
                error_percent=error_percent,
                mask=best.mask,
                active_bits=active_bits(best.mask),
            )

    def _check_safety_requested(self, resistance_ohm: float) -> None:
        if self.safety.min_resistance_ohm is not None and resistance_ohm < self.safety.min_resistance_ohm:
            raise SafetyLimitError(
                f"Requested resistance {resistance_ohm:g} Ω below safety minimum {self.safety.min_resistance_ohm:g} Ω"
            )
        if self.safety.max_resistance_ohm is not None and resistance_ohm > self.safety.max_resistance_ohm:
            raise SafetyLimitError(
                f"Requested resistance {resistance_ohm:g} Ω above safety maximum {self.safety.max_resistance_ohm:g} Ω"
            )

    def _check_safety_mask(self, mask: int | str) -> None:
        if self.safety.max_active_bits is not None and count_active_bits(mask) > self.safety.max_active_bits:
            raise SafetyLimitError(f"Mask {normalize_mask(mask)} exceeds max_active_bits={self.safety.max_active_bits}")
