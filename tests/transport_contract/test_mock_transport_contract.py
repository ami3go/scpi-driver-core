from __future__ import annotations

from contract import TransportContract

from scpi_driver_core.transport import MockTransport, Transport


class TestMockTransportContract(TransportContract):
    """MockTransport is the reference implementation, so it must pass everything."""

    supports_failure_injection = True
    supports_partial_write = True

    def create_transport(self) -> Transport:
        return MockTransport()

    def prime(self, transport: Transport, data: bytes) -> None:
        assert isinstance(transport, MockTransport)
        transport.feed(data)

    def inject_read_failure(self, transport: Transport, error: Exception) -> None:
        assert isinstance(transport, MockTransport)
        transport.fail_next_read(error)

    def create_fragmenting_transport(self, chunk_size: int) -> Transport:
        return MockTransport(max_write_chunk=chunk_size)
