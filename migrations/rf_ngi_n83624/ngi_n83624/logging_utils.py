"""Logging utilities for NGI N83624."""

from __future__ import annotations

import logging

LOGGER_NAME = "ngi_n83624"


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a package logger."""
    return logging.getLogger(LOGGER_NAME if name is None else f"{LOGGER_NAME}.{name}")


def configure_basic_logging(level: int = logging.INFO) -> None:
    """Configure simple console logging for examples and scripts."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
