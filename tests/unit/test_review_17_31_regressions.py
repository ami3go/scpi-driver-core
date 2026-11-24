from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest

import scpi_driver_core.transport.serial as serial_module
from scpi_driver_core.exceptions import TransportCleanupError, TransportError
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.session import ScpiSession, SessionRegistry
from scpi_driver_core.simulation import ScriptedScpiTransport
from scpi_driver_core.tracing import (
    InstrumentedTransport,
    JsonlTraceSink,
    PatternRedactor,
    RecordingTraceObserver,
    TraceDirection,
    Tracer,
)
from scpi_driver_core.transport import (
    MockTransport,
    SerialTransport,
    TcpTransport,
    TransportState,
    UdpTransport,
)


class FailOnceCloser:
    def __init__(self) -> None:
        self.close_calls = 0
        self.closed = False

    def close(self) -> None:
        self.close_calls += 1
        if self.close_calls == 1:
            raise OSError("close failed")
        self.closed = True


class FailOnceSocket(FailOnceCloser):
    def shutdown(self, how: int) -> None:
        del how


def test_serial_close_failure_retains_resource_for_retry() -> None:
    transport = SerialTransport("COM1")
    resource = FailOnceCloser()
    transport._resource = resource
    transport._set_state(TransportState.OPEN)

    with pytest.raises(TransportCleanupError):
        transport.close()

    assert transport.state is TransportState.FAULTED
    assert transport._resource is resource

    transport.close()
    assert transport.state is TransportState.CLOSED
    assert transport._resource is None
    assert resource.closed is True


def test_tcp_close_failure_retains_socket_for_retry() -> None:
    transport = TcpTransport("instrument", 5025)
    resource = FailOnceSocket()
    transport._socket = resource  # type: ignore[assignment]
    transport._set_state(TransportState.OPEN)

    with pytest.raises(TransportCleanupError):
        transport.close()

    assert transport.state is TransportState.FAULTED
    assert transport._socket is resource

    transport.close()
    assert transport.state is TransportState.CLOSED
    assert transport._socket is None
    assert resource.closed is True


def test_udp_close_failure_retains_socket_and_remote_for_retry() -> None:
    transport = UdpTransport("instrument", 5025)
    resource = FailOnceCloser()
    remote = ("127.0.0.1", 5025)
    transport._socket = resource  # type: ignore[assignment]
    transport._remote = remote
    transport._set_state(TransportState.OPEN)

    with pytest.raises(TransportCleanupError):
        transport.close()

    assert transport.state is TransportState.FAULTED
    assert transport._socket is resource
    assert transport._remote == remote

    transport.close()
    assert transport.state is TransportState.CLOSED
    assert transport._socket is None
    assert transport._remote is None


def test_serial_partial_open_preserves_primary_and_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenOpenSerial:
        def __init__(self) -> None:
            self.close_calls = 0

        def open(self) -> None:
            raise OSError("open failed")

        def close(self) -> None:
            self.close_calls += 1
            if self.close_calls == 1:
                raise OSError("cleanup failed")

    resource = BrokenOpenSerial()
    backend = SimpleNamespace(serial_for_url=lambda *_args, **_kwargs: resource)
    monkeypatch.setattr(serial_module, "_load_serial", lambda: backend)
    transport = SerialTransport("loop://")

    with pytest.raises(TransportError, match="open failed") as caught:
        transport.open()

    cleanup = getattr(caught.value, "cleanup_error", None)
    assert isinstance(cleanup, TransportCleanupError)
    assert transport.state is TransportState.FAULTED
    assert transport._resource is resource

    transport.close()
    assert transport.state is TransportState.CLOSED


def test_instrumented_context_preserves_body_exception_on_close_failure() -> None:
    inner = MockTransport()
    observer = RecordingTraceObserver()
    transport = InstrumentedTransport(inner, Tracer(observer))

    def boom() -> None:
        raise TransportError("trace close failed")

    inner.close = boom  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="primary") as caught:
        with transport:
            raise ValueError("primary")

    assert isinstance(getattr(caught.value, "cleanup_error", None), TransportError)


def test_scripted_context_preserves_body_exception_on_close_failure() -> None:
    transport = ScriptedScpiTransport()

    def boom() -> None:
        raise TransportError("scripted close failed")

    transport.inner.close = boom  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="primary") as caught:
        with transport:
            raise ValueError("primary")

    assert isinstance(getattr(caught.value, "cleanup_error", None), TransportError)


def test_registry_context_preserves_body_exception_on_disconnect_failure() -> None:
    transport = MockTransport()
    session = ScpiSession("psu", ScpiClient(transport))
    session.open()

    def boom() -> None:
        raise TransportError("registry close failed")

    transport.close = boom  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="primary") as caught:
        with SessionRegistry() as registry:
            registry.register("psu", session)
            raise ValueError("primary")

    assert isinstance(getattr(caught.value, "cleanup_error", None), TransportError)


class FailOnceFlushStream(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_flush = True

    def flush(self) -> None:
        if self.fail_next_flush:
            self.fail_next_flush = False
            raise OSError("flush failed")
        super().flush()


def test_jsonl_context_preserves_body_exception_on_finalize_failure() -> None:
    sink = JsonlTraceSink(FailOnceFlushStream())
    with pytest.raises(ValueError, match="primary") as caught:
        with sink:
            raise ValueError("primary")
    assert isinstance(getattr(caught.value, "cleanup_error", None), OSError)


def test_jsonl_failed_close_remains_retryable() -> None:
    stream = FailOnceFlushStream()
    sink = JsonlTraceSink(stream)

    with pytest.raises(OSError, match="flush failed"):
        sink.close()

    Tracer(sink).emit(TraceDirection.TX, data=b"*IDN?")
    sink.close()

    assert '"direction": "tx"' in stream.getvalue()
    assert stream.closed is False


def test_instrumented_transport_traces_addressed_gtl_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inner = MockTransport()
    calls: list[str] = []
    monkeypatch.setattr(
        inner,
        "go_to_local_addressed",
        lambda: calls.append("gtl"),
        raising=False,
    )
    observer = RecordingTraceObserver()
    transport = InstrumentedTransport(inner, Tracer(observer))
    transport.open()

    transport.go_to_local_addressed()  # type: ignore[attr-defined]

    assert calls == ["gtl"]
    event = observer.events[-1]
    assert event.direction is TraceDirection.CONTROL
    assert event.text == "go_to_local_addressed"


def test_trace_error_message_is_redacted() -> None:
    observer = RecordingTraceObserver()
    tracer = Tracer(observer, redactor=PatternRedactor([r"TOKEN=(\S+)"]))

    tracer.emit(
        TraceDirection.ERROR,
        success=False,
        error=TransportError("authentication failed TOKEN=hunter2"),
    )

    event = observer.events[-1]
    assert "hunter2" not in (event.error_message or "")
    assert event.redacted is True


def test_trace_error_redaction_fails_closed() -> None:
    class BrokenRedactor:
        def redact_command(self, command: str) -> str:
            del command
            raise RuntimeError("redactor failed")

        def redact_response(self, response: str, *, command: str | None = None) -> str:
            del response, command
            raise RuntimeError("redactor failed")

    observer = RecordingTraceObserver()
    tracer = Tracer(observer, redactor=BrokenRedactor())
    tracer.emit(
        TraceDirection.ERROR,
        success=False,
        error=TransportError("secret TOKEN=hunter2"),
    )

    event = observer.events[-1]
    assert event.error_message == "***"
    assert "hunter2" not in (event.error_message or "")
    assert event.redacted is True
