from __future__ import annotations

import importlib

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.transport import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    TransportState,
    VisaTransport,
)
from tests.transport_contract.test_visa_transport_contract import (
    FakeResourceManager,
    FakeVisaIOError,
    FakeVisaResource,
    install_fake_pyvisa,
)


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_pyvisa(monkeypatch)


def opened(fake_backend: None, **kwargs: object) -> VisaTransport:
    transport = VisaTransport("GPIB0::22::INSTR", **kwargs)  # type: ignore[arg-type]
    transport.open()
    return transport


# -- configuration --------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"resource_name": ""}, "resource_name"),
        ({"resource_name": "x", "timeout_s": 0}, "timeout_s"),
        ({"resource_name": "x", "timeout_s": float("inf")}, "timeout_s"),
        ({"resource_name": "x", "chunk_size": 0}, "chunk_size"),
    ],
)
def test_rejects_invalid_configuration(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        VisaTransport(**kwargs)  # type: ignore[arg-type]


def test_missing_pyvisa_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = importlib.import_module

    def missing(name: str) -> object:
        if name == "pyvisa":
            raise ImportError("missing")
        return real_import(name)

    monkeypatch.setattr(importlib, "import_module", missing)
    transport = VisaTransport("GPIB0::22::INSTR")
    with pytest.raises(ConfigurationError, match=r"\[visa\]") as caught:
        transport.open()
    assert caught.value.__cause__ is not None
    assert transport.state is TransportState.CREATED


def test_constructor_performs_no_io(fake_backend: None) -> None:
    """No resource opened, no manager created, no registry enumerated."""
    VisaTransport("GPIB0::22::INSTR")
    assert FakeResourceManager.instances == []
    assert FakeVisaResource.instances == []


def test_descriptor_is_available_before_open(fake_backend: None) -> None:
    transport = VisaTransport("TCPIP0::192.0.2.10::inst0::INSTR", visa_library="@py")
    assert transport.descriptor.kind == "visa"
    assert transport.descriptor.address == "TCPIP0::192.0.2.10::inst0::INSTR"
    assert transport.descriptor.metadata == {"visa_library": "@py"}


@pytest.mark.parametrize(
    "resource_name",
    [
        "GPIB0::22::INSTR",
        "USB0::0x0699::0x0368::C012345::INSTR",
        "TCPIP0::192.0.2.10::inst0::INSTR",
        "TCPIP0::192.0.2.10::5025::SOCKET",
        "ASRL5::INSTR",
    ],
)
def test_resource_name_is_passed_through_untouched(fake_backend: None, resource_name: str) -> None:
    transport = VisaTransport(resource_name)
    transport.open()
    assert FakeResourceManager.instances[-1].opened == [resource_name]


# -- session setup --------------------------------------------------------


def test_terminations_are_disabled_for_byte_fidelity(fake_backend: None) -> None:
    """PyVISA must not trim or append anything; the codec owns framing."""
    opened(fake_backend)
    settings = FakeVisaResource.instances[-1].settings
    assert settings["read_termination"] is None
    assert settings["write_termination"] is None


def test_timeout_is_converted_to_milliseconds(fake_backend: None) -> None:
    opened(fake_backend, timeout_s=2.5)
    assert FakeVisaResource.instances[-1].timeout == 2500.0


def test_per_call_timeout_is_converted_to_milliseconds(fake_backend: None) -> None:
    transport = opened(fake_backend, timeout_s=5.0)
    transport.write(b"*RST\n", timeout_s=0.25)
    assert FakeVisaResource.instances[-1].timeout == 250.0


def test_chunk_size_is_forwarded(fake_backend: None) -> None:
    opened(fake_backend, chunk_size=4096)
    assert FakeVisaResource.instances[-1].chunk_size == 4096


def test_visa_library_is_forwarded(fake_backend: None) -> None:
    transport = VisaTransport("GPIB0::22::INSTR", visa_library="@py")
    transport.open()
    assert FakeResourceManager.instances[-1].visa_library == "@py"


# -- resource-manager ownership -------------------------------------------


def test_owned_manager_is_closed_on_close(fake_backend: None) -> None:
    transport = opened(fake_backend)
    manager = FakeResourceManager.instances[-1]
    transport.close()
    assert manager.closed is True


def test_borrowed_manager_is_never_closed(fake_backend: None) -> None:
    """Its lifetime belongs to whoever created it."""
    borrowed = FakeResourceManager()
    transport = VisaTransport("GPIB0::22::INSTR", resource_manager=borrowed)
    transport.open()
    resource = FakeVisaResource.instances[-1]
    transport.close()
    assert borrowed.closed is False
    assert resource.closed is True


def test_borrowed_manager_skips_pyvisa_import(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode() -> object:
        raise AssertionError("must not import pyvisa when a manager is supplied")

    monkeypatch.setattr("scpi_driver_core.transport.visa._load_pyvisa", explode)
    transport = VisaTransport("GPIB0::22::INSTR", resource_manager=FakeResourceManager())
    transport.open()
    assert transport.is_open is True


# -- lifecycle ------------------------------------------------------------


def test_open_failure_faults_and_releases_the_manager(
    fake_backend: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: FakeResourceManager, name: str, **settings: object) -> object:
        raise FakeVisaIOError("VI_ERROR_RSRC_NFOUND", error_code=-1073807343)

    monkeypatch.setattr(FakeResourceManager, "open_resource", boom)
    transport = VisaTransport("GPIB0::99::INSTR")
    with pytest.raises(TransportError) as caught:
        transport.open()
    assert transport.state is TransportState.FAULTED
    assert not isinstance(caught.value, TransportTimeoutError)
    assert FakeResourceManager.instances[-1].closed is True


def test_reopen_from_faulted_closes_the_previous_resource(fake_backend: None) -> None:
    transport = opened(fake_backend)
    first = FakeVisaResource.instances[-1]
    transport.fail_next_read = None  # type: ignore[attr-defined]
    first.fail_read = TransportError("dead")
    with pytest.raises(TransportError):
        transport.read(ReadRequest(mode=ReadMode.AVAILABLE))

    assert first.closed is True
    transport.open()
    assert transport.is_open is True
    assert FakeVisaResource.instances[-1] is not first


def test_close_is_idempotent_and_closes_once(fake_backend: None) -> None:
    transport = opened(fake_backend)
    manager = FakeResourceManager.instances[-1]
    transport.close()
    transport.close()
    assert manager.closed is True
    assert len(FakeResourceManager.instances) == 1


# -- reads ----------------------------------------------------------------


def test_backend_defined_message_reads_exactly_one_message(fake_backend: None) -> None:
    """The mode exists for VISA; unlike TCP and serial it is honored here."""
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"FIRST\n")
    resource.feed(b"SECOND\n")
    request = ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)
    assert transport.read(request) == b"FIRST\n"
    assert transport.read(request) == b"SECOND\n"


def test_backend_defined_message_rejects_oversized_message(fake_backend: None) -> None:
    transport = opened(fake_backend)
    FakeVisaResource.instances[-1].feed(b"x" * 100)
    with pytest.raises(TransportError):
        transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE, maximum_size=10))


def test_exact_length_read_spans_message_boundaries(fake_backend: None) -> None:
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"ABC")
    resource.feed(b"DEF")
    assert transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=5)) == b"ABCDE"
    assert transport.read(ReadRequest(mode=ReadMode.AVAILABLE)) == b"F"


def test_terminator_search_spans_messages(fake_backend: None) -> None:
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"KEYSIGHT,")
    resource.feed(b"N6700C\n")
    data = transport.read(ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"))
    assert data == b"KEYSIGHT,N6700C"


def test_binary_payload_with_nulls_survives(fake_backend: None) -> None:
    payload = bytes(range(256)) + b"\x00\x00  \t  "
    transport = opened(fake_backend)
    FakeVisaResource.instances[-1].feed(payload)
    data = transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=len(payload)))
    assert data == payload


def test_open_is_idempotent_and_reuses_the_session(fake_backend: None) -> None:
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    transport.open()
    assert FakeVisaResource.instances[-1] is resource
    assert len(FakeVisaResource.instances) == 1


def test_failure_after_open_resource_still_closes_it(
    fake_backend: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The session exists but configuring it failed; it must not leak."""

    class ExplodingTimeout(FakeVisaResource):
        """Constructs cleanly, then refuses the timeout the transport applies."""

        def __init__(self, resource_name: str, **settings: object) -> None:
            self._armed = False
            self._timeout = 0.0
            super().__init__(resource_name, **settings)
            self._armed = True

        @property  # type: ignore[misc]
        def timeout(self) -> float:
            return self._timeout

        @timeout.setter
        def timeout(self, value: float) -> None:
            if self._armed:
                raise FakeVisaIOError("VI_ERROR_NSUP_ATTR", error_code=-1)
            self._timeout = value

    def open_resource(self: FakeResourceManager, name: str, **settings: object) -> object:
        return ExplodingTimeout(name, **settings)

    monkeypatch.setattr(FakeResourceManager, "open_resource", open_resource)
    transport = VisaTransport("GPIB0::22::INSTR")
    with pytest.raises(TransportError):
        transport.open()
    assert transport.state is TransportState.FAULTED
    assert FakeVisaResource.instances[-1].closed is True


def test_leftover_buffer_is_drained_before_reading_a_new_message(fake_backend: None) -> None:
    """A terminated read can leave bytes behind; they must be served first."""
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"1.5\nTRAILING")
    assert transport.read(ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")) == b"1.5"
    assert transport.read(ReadRequest(mode=ReadMode.BACKEND_DEFINED_MESSAGE)) == b"TRAILING"


def test_leftover_buffer_serves_available_without_touching_the_wire(
    fake_backend: None,
) -> None:
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"1.5\nEXTRA")
    transport.read(ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"))
    assert not resource.messages  # nothing left on the wire
    assert transport.read(ReadRequest(mode=ReadMode.AVAILABLE)) == b"EXTRA"


def test_terminated_message_beyond_maximum_size_is_rejected(fake_backend: None) -> None:
    """The terminator arrives, but only past the caller's bound."""
    transport = opened(fake_backend)
    FakeVisaResource.instances[-1].feed(b"x" * 40 + b"\n")
    with pytest.raises(TransportError) as caught:
        transport.read(
            ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n", maximum_size=16)
        )
    assert not isinstance(caught.value, TransportTimeoutError)


# -- error translation ----------------------------------------------------


def test_visa_timeout_becomes_transport_timeout(fake_backend: None) -> None:
    transport = opened(fake_backend)
    with pytest.raises(TransportTimeoutError) as caught:
        transport.read(ReadRequest(mode=ReadMode.AVAILABLE))
    assert isinstance(caught.value.__cause__, FakeVisaIOError)


def test_non_timeout_visa_error_becomes_transport_error(fake_backend: None) -> None:
    transport = opened(fake_backend)
    FakeVisaResource.instances[-1].fail_read = FakeVisaIOError("VI_ERROR_IO", error_code=-1)
    with pytest.raises(TransportError) as caught:
        transport.read(ReadRequest(mode=ReadMode.AVAILABLE))
    assert not isinstance(caught.value, TransportTimeoutError)
    assert caught.value.__cause__ is not None


def test_write_failure_faults_the_transport(fake_backend: None) -> None:
    transport = opened(fake_backend)

    def boom(data: bytes) -> int:
        raise FakeVisaIOError("VI_ERROR_IO", error_code=-1)

    FakeVisaResource.instances[-1].write_raw = boom  # type: ignore[method-assign]
    with pytest.raises(TransportError):
        transport.write(b"*RST\n")
    assert transport.state is TransportState.FAULTED


def test_write_that_makes_no_progress_times_out(fake_backend: None) -> None:
    transport = opened(fake_backend)
    FakeVisaResource.instances[-1].write_raw = lambda data: 0  # type: ignore[method-assign]
    with pytest.raises(TransportTimeoutError):
        transport.write(b"*RST\n")


def test_write_tolerates_a_backend_reporting_no_count(fake_backend: None) -> None:
    """Some PyVISA backends return None instead of a byte count."""
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]

    def write_none(data: bytes) -> None:
        resource.written.extend(data)
        return None

    resource.write_raw = write_none  # type: ignore[method-assign]
    assert transport.write(b"*RST\n").bytes_written == 5
    assert bytes(resource.written) == b"*RST\n"


# -- flush ----------------------------------------------------------------


@pytest.mark.parametrize("direction", [FlushDirection.INPUT, FlushDirection.BOTH])
def test_flush_clears_the_session(fake_backend: None, direction: FlushDirection) -> None:
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"stale\n")
    transport.flush(direction)
    assert resource.clears == 1


def test_flush_output_only_is_a_no_op(fake_backend: None) -> None:
    """VISA exposes only a whole-session clear, so this drops nothing."""
    transport = opened(fake_backend)
    resource = FakeVisaResource.instances[-1]
    resource.feed(b"keep\n")
    transport.flush(FlushDirection.OUTPUT)
    assert resource.clears == 0
    assert len(resource.messages) == 1


def test_flush_failure_faults_the_transport(fake_backend: None) -> None:
    transport = opened(fake_backend)

    def boom() -> None:
        raise FakeVisaIOError("VI_ERROR_IO", error_code=-1)

    FakeVisaResource.instances[-1].clear = boom  # type: ignore[method-assign]
    with pytest.raises(TransportError):
        transport.flush(FlushDirection.BOTH)
    assert transport.state is TransportState.FAULTED


def test_close_survives_a_backend_that_fails_to_close(fake_backend: None) -> None:
    """A failing close must not mask the reason we were closing."""
    transport = opened(fake_backend)

    def boom() -> None:
        raise FakeVisaIOError("VI_ERROR_IO", error_code=-1)

    FakeVisaResource.instances[-1].close = boom  # type: ignore[method-assign]
    transport.close()
    assert transport.state is TransportState.CLOSED
