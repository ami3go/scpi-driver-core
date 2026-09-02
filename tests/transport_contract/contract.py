"""The behavioral contract every Transport backend must satisfy.

Subclass :class:`TransportContract`, implement the hooks, and the whole suite
runs against that backend. This exists so TCP, UDP, serial, VISA and mock are
held to one definition of correct rather than each growing its own.

The class is deliberately not named ``Test*`` so pytest does not collect it
directly; only concrete subclasses run.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import ClassVar

import pytest

from scpi_driver_core.exceptions import (
    NotConnectedError,
    TransportError,
    TransportTimeoutError,
)
from scpi_driver_core.transport import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    Transport,
    TransportState,
)


class TransportContract:
    """Reusable conformance tests for a :class:`Transport` implementation."""

    #: Backends that cannot be made to fail on demand skip the fault tests.
    supports_failure_injection: ClassVar[bool] = False
    #: Backends that cannot simulate a fragmenting send skip the partial-write test.
    supports_partial_write: ClassVar[bool] = False

    # -- hooks ------------------------------------------------------------

    def create_transport(self) -> Transport:
        """Return a new, unopened transport."""
        raise NotImplementedError

    def prime(self, transport: Transport, data: bytes) -> None:
        """Arrange for ``data`` to become readable from ``transport``."""
        raise NotImplementedError

    def inject_read_failure(self, transport: Transport, error: Exception) -> None:
        """Arrange for the next read to fail with ``error`` and fault the transport."""
        raise NotImplementedError

    def create_fragmenting_transport(self, chunk_size: int) -> Transport:
        """Return a transport whose backend accepts ``chunk_size`` bytes per send."""
        raise NotImplementedError

    @pytest.fixture
    def transport(self) -> Iterator[Transport]:
        created = self.create_transport()
        try:
            yield created
        finally:
            created.close()

    # -- lifecycle --------------------------------------------------------

    def test_starts_created_and_not_open(self, transport: Transport) -> None:
        assert transport.state is TransportState.CREATED
        assert transport.is_open is False

    def test_open_reports_open_and_returns_descriptor(self, transport: Transport) -> None:
        descriptor = transport.open()
        assert transport.state is TransportState.OPEN
        assert transport.is_open is True
        assert descriptor == transport.descriptor

    def test_descriptor_is_available_before_open(self, transport: Transport) -> None:
        assert transport.descriptor.kind

    def test_close_reports_closed(self, transport: Transport) -> None:
        transport.open()
        transport.close()
        assert transport.state is TransportState.CLOSED
        assert transport.is_open is False

    def test_close_is_idempotent(self, transport: Transport) -> None:
        transport.open()
        transport.close()
        transport.close()
        transport.close()
        assert transport.state is TransportState.CLOSED

    def test_close_before_open_is_harmless(self, transport: Transport) -> None:
        transport.close()
        assert transport.is_open is False

    def test_reopen_after_close(self, transport: Transport) -> None:
        transport.open()
        transport.close()
        transport.open()
        assert transport.is_open is True

    # -- I/O is refused unless open ---------------------------------------

    def test_write_before_open_raises(self, transport: Transport) -> None:
        with pytest.raises(NotConnectedError):
            transport.write(b"*IDN?\n")

    def test_read_before_open_raises(self, transport: Transport) -> None:
        with pytest.raises(NotConnectedError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE))

    def test_transact_before_open_raises(self, transport: Transport) -> None:
        with pytest.raises(NotConnectedError):
            transport.transact(b"*IDN?\n", ReadRequest(mode=ReadMode.AVAILABLE))

    def test_flush_before_open_raises(self, transport: Transport) -> None:
        with pytest.raises(NotConnectedError):
            transport.flush(FlushDirection.BOTH)

    def test_write_after_close_raises(self, transport: Transport) -> None:
        transport.open()
        transport.close()
        with pytest.raises(NotConnectedError):
            transport.write(b"*IDN?\n")

    def test_read_after_close_raises(self, transport: Transport) -> None:
        transport.open()
        transport.close()
        with pytest.raises(NotConnectedError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE))

    # -- reads are bounded and exact --------------------------------------

    def test_read_until_terminator_strips_it_by_default(self, transport: Transport) -> None:
        transport.open()
        self.prime(transport, b"KEYSIGHT,N6700C\n")
        data = transport.read(ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"))
        assert data == b"KEYSIGHT,N6700C"

    def test_read_until_terminator_can_keep_it(self, transport: Transport) -> None:
        transport.open()
        self.prime(transport, b"KEYSIGHT,N6700C\n")
        data = transport.read(
            ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n", include_terminator=True)
        )
        assert data == b"KEYSIGHT,N6700C\n"

    def test_read_exact_length(self, transport: Transport) -> None:
        transport.open()
        self.prime(transport, b"0123456789")
        assert transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=4)) == b"0123"

    def test_read_up_to_length_returns_what_is_there(self, transport: Transport) -> None:
        transport.open()
        self.prime(transport, b"abc")
        data = transport.read(ReadRequest(mode=ReadMode.UP_TO_LENGTH, length=64))
        assert data == b"abc"

    def test_read_without_data_times_out_promptly(self, transport: Transport) -> None:
        transport.open()
        with pytest.raises(TransportTimeoutError):
            transport.read(
                ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"),
                timeout_s=0.25,
            )

    def test_read_rejects_response_larger_than_maximum_size(self, transport: Transport) -> None:
        transport.open()
        self.prime(transport, b"x" * 64)
        with pytest.raises(TransportError):
            transport.read(
                ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n", maximum_size=16)
            )

    def test_binary_payload_survives_intact(self, transport: Transport) -> None:
        payload = bytes(range(256)) + b"  \t trailing spaces  \x00\x00"
        transport.open()
        self.prime(transport, payload)
        data = transport.read(ReadRequest(mode=ReadMode.EXACT_LENGTH, length=len(payload)))
        assert data == payload

    # -- writes -----------------------------------------------------------

    def test_write_reports_full_length(self, transport: Transport) -> None:
        transport.open()
        result = transport.write(b"VOLT 12.5\n")
        assert result.bytes_written == len(b"VOLT 12.5\n")

    def test_write_accepts_empty_payload(self, transport: Transport) -> None:
        transport.open()
        assert transport.write(b"").bytes_written == 0

    def test_partial_write_still_delivers_everything(self) -> None:
        if not self.supports_partial_write:
            pytest.skip("backend cannot simulate a fragmenting send")
        transport = self.create_fragmenting_transport(3)
        try:
            transport.open()
            payload = b"0123456789"
            assert transport.write(payload).bytes_written == len(payload)
        finally:
            transport.close()

    # -- transactions -----------------------------------------------------

    def test_transact_returns_the_response(self, transport: Transport) -> None:
        transport.open()
        self.prime(transport, b"1.234\n")
        data = transport.transact(
            b"MEAS:VOLT?\n", ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")
        )
        assert data == b"1.234"

    def test_concurrent_transactions_do_not_lose_responses(self, transport: Transport) -> None:
        count = 24
        transport.open()
        for _ in range(count):
            self.prime(transport, b"OK\n")

        received: list[bytes] = []
        received_lock = threading.Lock()
        errors: list[BaseException] = []

        def run() -> None:
            try:
                data = transport.transact(
                    b"MEAS?\n",
                    ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"),
                )
            except BaseException as exc:  # noqa: BLE001 - reported, not swallowed
                with received_lock:
                    errors.append(exc)
                return
            with received_lock:
                received.append(data)

        threads = [threading.Thread(target=run) for _ in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert not errors
        assert received == [b"OK"] * count

    # -- faults -----------------------------------------------------------

    def test_failure_faults_the_transport(self, transport: Transport) -> None:
        if not self.supports_failure_injection:
            pytest.skip("backend cannot inject failures")
        transport.open()
        self.inject_read_failure(transport, TransportError("backend exploded"))
        with pytest.raises(TransportError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE))
        assert transport.state is TransportState.FAULTED
        assert transport.is_open is False

    def test_io_while_faulted_is_refused(self, transport: Transport) -> None:
        if not self.supports_failure_injection:
            pytest.skip("backend cannot inject failures")
        transport.open()
        self.inject_read_failure(transport, TransportError("backend exploded"))
        with pytest.raises(TransportError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE))
        with pytest.raises(NotConnectedError):
            transport.write(b"*RST\n")

    def test_reopen_recovers_from_faulted(self, transport: Transport) -> None:
        if not self.supports_failure_injection:
            pytest.skip("backend cannot inject failures")
        transport.open()
        self.inject_read_failure(transport, TransportError("backend exploded"))
        with pytest.raises(TransportError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE))
        transport.open()
        assert transport.state is TransportState.OPEN

    def test_close_from_faulted_reaches_closed(self, transport: Transport) -> None:
        if not self.supports_failure_injection:
            pytest.skip("backend cannot inject failures")
        transport.open()
        self.inject_read_failure(transport, TransportError("backend exploded"))
        with pytest.raises(TransportError):
            transport.read(ReadRequest(mode=ReadMode.AVAILABLE))
        transport.close()
        assert transport.state is TransportState.CLOSED
