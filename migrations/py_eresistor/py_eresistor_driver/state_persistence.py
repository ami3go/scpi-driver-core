"""Atomic JSON state persistence."""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import OutputSnapshot


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def save_json_atomic(path: str | Path, data: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=_json_default), encoding="utf-8")
    os.replace(tmp, p)


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_snapshot(path: str | Path, snapshot: OutputSnapshot) -> None:
    save_json_atomic(path, asdict(snapshot))


def load_snapshot(path: str | Path) -> OutputSnapshot:
    data = load_json(path)
    masks = {int(k): v for k, v in data["masks"].items()}
    created_at = datetime.fromisoformat(data["created_at"])
    return OutputSnapshot(masks=masks, created_at=created_at, source=data.get("source", "file"))
