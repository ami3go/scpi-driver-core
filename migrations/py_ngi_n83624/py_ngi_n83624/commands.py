"""Command-string helpers for the NGI N83624 SCPI dialect."""

from __future__ import annotations

from collections.abc import Sequence

from .parsing import format_channel_list
from .safety import validate_channel, validate_channels


def ch(prefix: str, channel: int, suffix: str) -> str:
    """Build ``PREFIX<n>:SUFFIX`` after validating ``channel``."""
    validate_channel(channel)
    return f"{prefix}{channel}:{suffix}"


def batch_query(root: str, quantity: str, channels: Sequence[int]) -> str:
    """Build a documented batch query such as ``MEASure:VOLTage?(@1,2)``."""
    validated = validate_channels(channels)
    return f"{root}:{quantity}?{format_channel_list(validated)}"
