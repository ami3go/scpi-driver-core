"""Connecting to real hardware, over each supported transport.

Unlike the other examples this one is illustrative: it needs an instrument on
the other end, so it is not run by the test suite. The code above the transport
choice is identical in every case, which is the property the package exists to
provide.
"""

from __future__ import annotations

from scpi_driver_core import ScpiClient, ScpiSession
from scpi_driver_core.models import Identity
from scpi_driver_core.scpi import ScpiTextCodec
from scpi_driver_core.transport import (
    SerialTransport,
    TcpTransport,
    UdpTransport,
    VisaTransport,
)


def visa_session() -> ScpiSession:
    """GPIB, USBTMC, TCPIP INSTR/SOCKET and ASRL all use this one class."""
    transport = VisaTransport("TCPIP0::192.0.2.10::inst0::INSTR", timeout_s=5.0)
    # VISA frames its own messages, so the codec adds no response terminator.
    codec = ScpiTextCodec(response_terminator=None)
    return ScpiSession("dmm", ScpiClient(transport, codec=codec))


def tcp_session() -> ScpiSession:
    """A raw socket instrument, such as an N6700 on port 5025."""
    transport = TcpTransport(host="192.0.2.10", port=5025, timeout_s=5.0)
    return ScpiSession("psu", ScpiClient(transport))


def udp_session() -> ScpiSession:
    """Datagram instruments, such as the N83624."""
    transport = UdpTransport(host="192.0.2.20", port=5025, timeout_s=2.0)
    return ScpiSession("load", ScpiClient(transport))


def serial_session() -> ScpiSession:
    transport = SerialTransport("/dev/ttyUSB0", baudrate=9600, timeout_s=5.0)
    codec = ScpiTextCodec(command_terminator=b"\r\n", response_terminator=b"\r\n")
    return ScpiSession("scope", ScpiClient(transport, codec=codec))


def require_model(expected: str):  # type: ignore[no-untyped-def]
    """Identity validation belongs to the driver, never to the core."""

    def validate(identity: Identity) -> None:
        if expected not in identity.model:
            raise RuntimeError(f"expected {expected}, found {identity.model}")

    return validate


def main() -> None:
    session = tcp_session()
    # probe fails fast if the socket opens but nothing answers on it
    session.open(probe=True, validate_identity=require_model("N6700"))
    try:
        print(session.get_identity())
        print(session.client.query_float("MEAS:VOLT? (@1)"))
    finally:
        session.close()


if __name__ == "__main__":
    main()
