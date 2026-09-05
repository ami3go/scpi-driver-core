"""Logging helpers, including optional JSON-style structured logging."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process",
            }:
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = repr(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def configure_logging(level: str = "INFO", structured: bool = False) -> None:
    handler = logging.StreamHandler(sys.stderr)
    if structured:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


class AuditLogger:
    def __init__(self, path: str | None = None) -> None:
        self._logger = logging.getLogger("eresistor_driver.audit")
        self._handler: logging.Handler | None = None
        if path:
            self._handler = logging.FileHandler(path, encoding="utf-8")
            self._handler.setFormatter(JsonFormatter())
            self._logger.addHandler(self._handler)
            self._logger.propagate = False
            self._logger.setLevel(logging.INFO)

    def log_command(self, command: str, response: str | None, status: str, **extra: Any) -> None:
        self._logger.info(
            "state_changing_command",
            extra={"command": command, "response": response, "status": status, **extra},
        )

    def close(self) -> None:
        if self._handler:
            self._logger.removeHandler(self._handler)
            self._handler.close()
            self._handler = None
