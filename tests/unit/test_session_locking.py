from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from scpi_driver_core import ScpiClient, ScpiSession
from scpi_driver_core.models import Identity
from scpi_driver_core.transport import MockTransport


class _RecordingLock:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def __enter__(self) -> _RecordingLock:
        self._events.append("session-enter")
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._events.append("session-exit")


class _StubIeee488:
    def identify(self) -> Identity:
        return Identity(
            manufacturer="ACME",
            model="MODEL",
            serial_number="123",
            firmware_version="1.0",
            raw="ACME,MODEL,123,1.0",
        )


@contextmanager
def _record_client_lock(events: list[str]) -> Iterator[None]:
    events.append("client-enter")
    try:
        yield
    finally:
        events.append("client-exit")


def _install_lock_recorders(session: ScpiSession, client: ScpiClient, events: list[str]) -> None:
    def operation_lock() -> object:
        return _record_client_lock(events)

    client.operation_lock = operation_lock  # type: ignore[method-assign]
    session._lock = _RecordingLock(events)  # type: ignore[assignment]


def test_identity_acquires_client_lock_before_session_lock() -> None:
    """Regression: session->client ordering could deadlock retry recovery."""
    client = ScpiClient(MockTransport())
    session = ScpiSession("scope", client)
    events: list[str] = []
    _install_lock_recorders(session, client, events)
    session._ieee488 = _StubIeee488()  # type: ignore[assignment]

    assert session.get_identity().model == "MODEL"
    assert events == ["client-enter", "session-enter", "session-exit", "client-exit"]


def test_retry_recovery_uses_same_client_then_session_lock_order() -> None:
    """The before-retry callback must follow the same cross-layer lock order."""
    client = ScpiClient(MockTransport())
    session = ScpiSession("scope", client)
    events: list[str] = []
    _install_lock_recorders(session, client, events)

    session.recover_if_faulted()

    assert session.is_connected
    assert events == ["client-enter", "session-enter", "session-exit", "client-exit"]
