"""Transport abstraction and the deterministic FakeTransport (spec sections 5, 21).

Shared transport rules (21.1):
  * ASCII encoding by default.
  * Append the write terminator to commands.
  * Strip response terminators (raw text preserved by callers).
  * Serialize all traffic through a lock.
  * Enforce one outstanding query at a time.
  * Provide a clear() operation.
  * Expose a name/resource for logs.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Protocol, runtime_checkable

from .enums import TransportType
from .errors import ProtocolError, TransportError

_log = logging.getLogger("hp34401a_dmm.transport")


@runtime_checkable
class Transport(Protocol):
    """Low-level byte/line transport contract used by the driver."""

    @property
    def name(self) -> str: ...

    @property
    def transport_type(self) -> TransportType: ...

    def open(self) -> None: ...

    def close(self) -> None: ...

    def is_open(self) -> bool: ...

    def write(self, command: str) -> None: ...

    def query(self, command: str) -> str: ...

    def read_raw(self) -> str: ...

    def write_raw(self, data: str) -> None: ...

    def clear(self) -> None: ...

    def set_timeout(self, timeout_s: float) -> None: ...


class BaseTransport:
    """Common locking, terminator handling and one-outstanding-query enforcement.

    Concrete transports implement the ``_send`` / ``_recv`` / ``_clear`` /
    ``_open`` / ``_close`` hooks; this base owns the cross-cutting rules so the
    behaviour is identical across serial and VISA.
    """

    _transport_type: TransportType = TransportType.FAKE

    def __init__(
        self,
        *,
        read_termination: str = "\n",
        write_termination: str = "\n",
        encoding: str = "ascii",
        raw_traffic_log: bool = False,
    ) -> None:
        self._read_termination = read_termination
        self._write_termination = write_termination
        self._encoding = encoding
        self._raw_traffic_log = raw_traffic_log
        self._lock = threading.RLock()
        self._has_unread_output = False
        self._open = False

    # -- properties ---------------------------------------------------------
    @property
    def transport_type(self) -> TransportType:
        return self._transport_type

    @property
    def name(self) -> str:  # pragma: no cover - overridden
        return "base"

    def is_open(self) -> bool:
        return self._open

    # -- public API ---------------------------------------------------------
    def write(self, command: str) -> None:
        with self._lock:
            if self._has_unread_output:
                raise ProtocolError(
                    "Refusing to write a command while a previous query response "
                    "is unread (one-outstanding-query rule)."
                )
            self._log_traffic("WRITE", command)
            self._send(command + self._write_termination)

    def query(self, command: str) -> str:
        with self._lock:
            if self._has_unread_output:
                raise ProtocolError(
                    "Refusing to send a query while a previous query response is "
                    "unread (one-outstanding-query rule)."
                )
            t0 = time.monotonic()
            self._send(command + self._write_termination)
            self._has_unread_output = True
            try:
                response = self._recv()
            except Exception:
                # A real instrument can still send the response after the PC-side
                # timeout. Keep the unread-output flag set until clear()/read_raw()
                # is used so the driver cannot accidentally send another query and
                # read stale data or create a query-interrupted condition.
                raise
            else:
                self._has_unread_output = False
            stripped = response.rstrip("\r\n")
            self._log_traffic("QUERY", command, stripped, time.monotonic() - t0)
            return stripped

    def read_raw(self) -> str:
        """Recovery-only raw read. Does not enforce the query rule."""
        with self._lock:
            data = self._recv()
            self._has_unread_output = False
            return data

    def write_raw(self, data: str) -> None:
        """Recovery-only raw write (e.g. Ctrl-C). Does not append a terminator."""
        with self._lock:
            self._log_traffic("RAW", data)
            self._send(data)

    def clear(self) -> None:
        with self._lock:
            self._clear()
            self._has_unread_output = False

    def open(self) -> None:
        with self._lock:
            try:
                self._do_open()
            except Exception:
                self._open = False
                self._has_unread_output = False
                try:
                    self._do_close()
                except Exception:
                    pass
                raise
            self._open = True

    def close(self) -> None:
        with self._lock:
            try:
                self._do_close()
            finally:
                self._open = False
                self._has_unread_output = False

    def set_timeout(self, timeout_s: float) -> None:
        with self._lock:
            self._set_timeout(timeout_s)

    @property
    def lock(self) -> threading.RLock:
        return self._lock

    # -- hooks (override) ---------------------------------------------------
    def _send(self, data: str) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _recv(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def _clear(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _do_open(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _do_close(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def _set_timeout(self, timeout_s: float) -> None:  # pragma: no cover
        raise NotImplementedError

    # -- helpers ------------------------------------------------------------
    def _log_traffic(
        self, kind: str, command: str, response: str | None = None, dur: float | None = None
    ) -> None:
        if not self._raw_traffic_log:
            return
        if response is None:
            _log.debug("[%s] %s -> %r", self.name, kind, command)
        else:
            _log.debug(
                "[%s] %s %r => %r (%.3fs)", self.name, kind, command, response, dur or 0.0
            )


class FakeTransport(BaseTransport):
    """Scriptable, deterministic transport for unit tests (spec sections 2, 29).

    * ``responses`` maps an exact command string to a canned response.
    * ``default_response`` is returned for any unmatched query.
    * ``error_queue`` simulates the instrument FIFO error queue; SYSTem:ERRor?
      pops from it (returning '+0,"No error"' when empty).
    * ``history`` records every command written/queried in order so tests can
      assert on exact SCPI sequencing.
    * ``timeout_on`` is a set of commands that raise InstrumentTimeoutError to
      exercise recovery paths.
    """

    _transport_type = TransportType.FAKE

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        default_response: str = "",
        error_queue: list[str] | None = None,
        idn: str = "HEWLETT-PACKARD,34401A,0,11-05-01",
        raw_traffic_log: bool = False,
    ) -> None:
        super().__init__(raw_traffic_log=raw_traffic_log)
        self.responses = responses or {}
        self.default_response = default_response
        self.error_queue: list[str] = list(error_queue or [])
        self.idn = idn
        self.history: list[str] = []
        self.write_history: list[str] = []
        self.query_history: list[str] = []
        self.response_history: list[tuple[str, str]] = []
        self.clear_count = 0
        self.raw_writes: list[str] = []
        self.timeout_on: set[str] = set()
        from .errors import InstrumentTimeoutError  # local import to avoid cycle

        self._TimeoutError = InstrumentTimeoutError

    @property
    def name(self) -> str:
        return "fake"

    # The fake overrides write/query directly (it is line-oriented, not byte).
    def write(self, command: str) -> None:
        with self._lock:
            if self._has_unread_output:
                raise ProtocolError("Write while query response unread (fake).")
            self.history.append(command)
            self.write_history.append(command)
            if command in self.timeout_on:
                raise self._TimeoutError(f"Fake timeout on {command!r}")

    def query(self, command: str) -> str:
        with self._lock:
            if self._has_unread_output:
                raise ProtocolError("Query while previous response unread (fake).")
            self.history.append(command)
            self.query_history.append(command)
            if command in self.timeout_on:
                # Model a real timeout: response stays 'outstanding' until cleared.
                self._has_unread_output = True
                raise self._TimeoutError(f"Fake timeout on {command!r}")
            response = self._respond(command)
            self.response_history.append((command, response))
            return response

    def _respond(self, command: str) -> str:
        if command == "*IDN?":
            return self.idn
        if command == "SYSTem:ERRor?":
            return self.error_queue.pop(0) if self.error_queue else '+0,"No error"'
        if command in self.responses:
            return self.responses[command]
        return self.default_response

    def read_raw(self) -> str:
        with self._lock:
            self._has_unread_output = False
            return self.default_response

    def write_raw(self, data: str) -> None:
        with self._lock:
            self.raw_writes.append(data)

    def clear(self) -> None:
        with self._lock:
            self.clear_count += 1
            self._has_unread_output = False

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False
        self._has_unread_output = False

    def set_timeout(self, timeout_s: float) -> None:
        pass
