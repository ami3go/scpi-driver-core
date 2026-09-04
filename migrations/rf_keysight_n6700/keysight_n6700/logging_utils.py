"""Logging helpers."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_rotating_log(path: str | Path, *, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("keysight_n6700")
    logger.setLevel(level)
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    return logger
