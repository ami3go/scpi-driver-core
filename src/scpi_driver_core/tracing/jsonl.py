"""Append-only JSONL protocol audit."""

from __future__ import annotations

import base64
import json
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Final

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.tracing.events import ProtocolTraceEvent

__all__ = ["SCHEMA_VERSION", "JsonlTraceSink"]

SCHEMA_VERSION: Final = 1
DEFAULT_MAXIMUM_PAYLOAD_BYTES: Final = 4096


class JsonlTraceSink:
    """Write trace events as JSON lines.

    ``flush_each_event`` reaches the Python stream. ``fsync_each_event`` is a
    stronger opt-in durability mode that also asks the OS to persist the file;
    it is intentionally off by default because it is expensive.
    """

    def __init__(
        self,
        destination: str | Path | IO[str],
        *,
        include_payloads: bool = True,
        maximum_payload_bytes: int = DEFAULT_MAXIMUM_PAYLOAD_BYTES,
        flush_each_event: bool = True,
        fsync_each_event: bool = False,
    ) -> None:
        if maximum_payload_bytes <= 0:
            raise ConfigurationError("maximum_payload_bytes must be positive")
        self._include_payloads = include_payloads
        self._maximum_payload_bytes = maximum_payload_bytes
        self._flush_each_event = flush_each_event
        self._fsync_each_event = fsync_each_event
        self._lock = threading.Lock()
        self._closed = False
        if isinstance(destination, (str, Path)):
            self._stream: IO[str] = open(destination, "a", encoding="utf-8")  # noqa: SIM115
            self._owns_stream = True
        else:
            self._stream = destination
            self._owns_stream = False

    def on_event(self, event: ProtocolTraceEvent) -> None:
        with self._lock:
            if self._closed:
                return
            self._stream.write(json.dumps(self.to_record(event), sort_keys=True) + "\n")
            if self._flush_each_event or self._fsync_each_event:
                self._stream.flush()
            if self._fsync_each_event:
                os.fsync(self._stream.fileno())

    def to_record(self, event: ProtocolTraceEvent) -> dict[str, Any]:
        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "sequence": event.sequence,
            "direction": event.direction.value,
            "timestamp_utc": event.timestamp_utc.isoformat(),
            "monotonic_s": event.monotonic_s,
            "success": event.success,
        }
        if event.duration_s is not None:
            record["duration_s"] = event.duration_s
        if event.operation_id is not None:
            record["operation_id"] = event.operation_id
        if event.context.session_alias is not None:
            record["session_alias"] = event.context.session_alias
        if event.context.session_generation is not None:
            record["session_generation"] = event.context.session_generation
        if event.descriptor is not None:
            record["transport"] = _descriptor_record(event.descriptor)
        if event.redacted:
            record["redacted"] = True
        if event.error_category is not None:
            record["error_category"] = event.error_category
            record["error_message"] = event.error_message
        if self._include_payloads and event.data:
            payload = event.data
            record["payload_length"] = len(payload)
            if len(payload) > self._maximum_payload_bytes:
                payload = payload[: self._maximum_payload_bytes]
                record["payload_truncated"] = True
            record["payload_base64"] = base64.b64encode(payload).decode("ascii")
            if event.text is not None:
                record["text"] = event.text[: self._maximum_payload_bytes]
        return record

    def flush(self) -> None:
        with self._lock:
            if not self._closed:
                self._stream.flush()
                if self._fsync_each_event:
                    os.fsync(self._stream.fileno())

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stream.flush()
            if self._fsync_each_event:
                os.fsync(self._stream.fileno())
            if self._owns_stream:
                self._stream.close()

    def __enter__(self) -> JsonlTraceSink:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()


def _descriptor_record(descriptor: Any) -> Mapping[str, Any]:
    record: dict[str, Any] = {"kind": descriptor.kind, "address": descriptor.address}
    if descriptor.metadata:
        record["metadata"] = dict(descriptor.metadata)
    return record
