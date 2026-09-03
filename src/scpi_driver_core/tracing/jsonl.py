"""Append-only JSONL protocol audit.

One JSON object per line, appended and never rewritten, so a file remains
readable after a crash and can be tailed while a run is in progress. Every
record carries a schema version, because an audit file outlives the code that
wrote it.

Binary is base64, chosen so a waveform round-trips exactly and the encoding is
deterministic rather than dependent on a repr.

This is protocol-level audit, not a test-run evidence system. It records what
crossed the wire, not what a test concluded.
"""

from __future__ import annotations

import base64
import json
import threading
from collections.abc import Mapping
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Final

from scpi_driver_core.tracing.events import ProtocolTraceEvent

__all__ = ["SCHEMA_VERSION", "JsonlTraceSink"]

SCHEMA_VERSION: Final = 1

DEFAULT_MAXIMUM_PAYLOAD_BYTES: Final = 4096


class JsonlTraceSink:
    """Writes trace events to a JSONL file or stream.

    Args:
        destination: a path to append to, or an already-open text stream. A
            stream passed in is not closed by this sink, since its lifetime
            belongs to whoever opened it.
        include_payloads: whether to record payload bytes at all. Turn it off
            where even redacted traffic should not be persisted.
        maximum_payload_bytes: payloads longer than this are truncated, with
            the original length kept in ``payload_length``. A megabyte waveform
            would otherwise dwarf everything else in the file.
        flush_each_event: flush after every write, so a crash loses nothing.
            Off makes a long run measurably faster at that risk.
    """

    def __init__(
        self,
        destination: str | Path | IO[str],
        *,
        include_payloads: bool = True,
        maximum_payload_bytes: int = DEFAULT_MAXIMUM_PAYLOAD_BYTES,
        flush_each_event: bool = True,
    ) -> None:
        self._include_payloads = include_payloads
        self._maximum_payload_bytes = maximum_payload_bytes
        self._flush_each_event = flush_each_event
        self._lock = threading.Lock()
        self._closed = False

        if isinstance(destination, (str, Path)):
            # Held open for the sink's lifetime and closed by close();
            # a context manager here would close it immediately.
            self._stream: IO[str] = open(  # noqa: SIM115
                destination, "a", encoding="utf-8"
            )
            self._owns_stream = True
        else:
            self._stream = destination
            self._owns_stream = False

    # -- observer interface -----------------------------------------------

    def on_event(self, event: ProtocolTraceEvent) -> None:
        """Append ``event`` as one JSON line.

        Writing to a closed sink is ignored rather than raised: a trace sink
        must not turn shutdown ordering into an instrument failure.
        """
        with self._lock:
            if self._closed:
                return
            self._stream.write(json.dumps(self.to_record(event), sort_keys=True) + "\n")
            if self._flush_each_event:
                self._stream.flush()

    # -- serialization ----------------------------------------------------

    def to_record(self, event: ProtocolTraceEvent) -> dict[str, Any]:
        """Render ``event`` as the mapping written to the file."""
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

    # -- lifetime ---------------------------------------------------------

    def flush(self) -> None:
        """Push buffered records to the underlying stream."""
        with self._lock:
            if not self._closed:
                self._stream.flush()

    def close(self) -> None:
        """Flush and finalize. Idempotent, and never closes a borrowed stream."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._stream.flush()
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
