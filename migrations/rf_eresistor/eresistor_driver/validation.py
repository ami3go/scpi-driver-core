"""Input validation helpers."""
from __future__ import annotations

from .exceptions import EResistorError

CHANNEL_COUNT = 8
MASK_MAX = 0xFFFF


def validate_channel(channel: int) -> int:
    if not isinstance(channel, int):
        raise ValueError(f"channel must be int 1..{CHANNEL_COUNT}, got {channel!r}")
    if channel < 1 or channel > CHANNEL_COUNT:
        raise ValueError(f"channel must be in range 1..{CHANNEL_COUNT}, got {channel}")
    return channel


def normalize_mask(mask: int | str) -> str:
    if isinstance(mask, int):
        value = mask
    elif isinstance(mask, str):
        text = mask.strip().upper()
        if text.startswith("0X"):
            text = text[2:]
        if len(text) == 0 or len(text) > 4:
            raise ValueError(f"mask must be 1..4 hexadecimal digits, got {mask!r}")
        try:
            value = int(text, 16)
        except ValueError as exc:
            raise ValueError(f"mask must be hexadecimal, got {mask!r}") from exc
    else:
        raise ValueError(f"mask must be int or hex string, got {type(mask).__name__}")

    if value < 0 or value > MASK_MAX:
        raise ValueError(f"mask must be 0..0xFFFF, got {value!r}")
    return f"{value:04X}"


def mask_to_int(mask: int | str) -> int:
    return int(normalize_mask(mask), 16)


def active_bits(mask: int | str) -> list[int]:
    value = mask_to_int(mask)
    return [bit for bit in range(16) if value & (1 << bit)]


def count_active_bits(mask: int | str) -> int:
    return mask_to_int(mask).bit_count()


def normalize_all_masks(masks: list[int | str] | tuple[int | str, ...]) -> list[str]:
    if len(masks) != CHANNEL_COUNT:
        raise ValueError(f"exactly {CHANNEL_COUNT} masks are required")
    return [normalize_mask(m) for m in masks]


def parse_idn(idn: str) -> tuple[str | None, str | None]:
    parts = [p.strip() for p in idn.strip().split(",")]
    serial = parts[2] if len(parts) >= 3 else None
    firmware = parts[3] if len(parts) >= 4 else None
    return serial, firmware
