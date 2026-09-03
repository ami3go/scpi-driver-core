from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    IdentityError,
    OperationTimeoutError,
    ResponseParseError,
    TransportTimeoutError,
)
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.scpi.ieee488 import Ieee4882
from scpi_driver_core.transport import MockTransport


def make(*replies: bytes) -> tuple[Ieee4882, MockTransport]:
    transport = MockTransport()
    transport.open()
    for reply in replies:
        transport.feed(reply)
    return Ieee4882(ScpiClient(transport)), transport


# -- identity -------------------------------------------------------------


def test_identify_parses_the_reply() -> None:
    ieee, transport = make(b"KEYSIGHT,N6700C,MY56000102,D.01.09\n")
    identity = ieee.identify()
    assert transport.written == b"*IDN?\n"
    assert identity.manufacturer == "KEYSIGHT"
    assert identity.model == "N6700C"
    assert identity.serial_number == "MY56000102"
    assert identity.firmware_version == "D.01.09"


def test_identify_rejects_an_unusable_reply() -> None:
    ieee, _ = make(b"???\n")
    with pytest.raises(IdentityError):
        ieee.identify()


def test_identify_does_not_validate_the_manufacturer() -> None:
    """Deciding whether this is the right instrument is the driver's job."""
    ieee, _ = make(b"SOME-OTHER-VENDOR,XYZ,1,2\n")
    assert ieee.identify().manufacturer == "SOME-OTHER-VENDOR"


# -- write-only commands --------------------------------------------------


@pytest.mark.parametrize(
    ("method", "command"),
    [
        ("clear_status", b"*CLS\n"),
        ("reset", b"*RST\n"),
        ("set_operation_complete", b"*OPC\n"),
        ("wait", b"*WAI\n"),
        ("trigger", b"*TRG\n"),
    ],
)
def test_write_only_commands(method: str, command: bytes) -> None:
    ieee, transport = make()
    getattr(ieee, method)()
    assert transport.written == command


def test_write_only_commands_read_nothing_back() -> None:
    ieee, transport = make()
    ieee.wait()
    assert [op.kind for op in transport.operations if op.kind == "read"] == []


# -- synchronization ------------------------------------------------------


def test_operation_complete_true() -> None:
    ieee, transport = make(b"1\n")
    assert ieee.operation_complete() is True
    assert transport.written == b"*OPC?\n"


def test_operation_complete_false() -> None:
    ieee, _ = make(b"0\n")
    assert ieee.operation_complete() is False


def test_wait_operation_complete_returns_on_success() -> None:
    ieee, transport = make(b"1\n")
    ieee.wait_operation_complete(2.0)
    assert transport.written == b"*OPC?\n"


def test_wait_operation_complete_forwards_its_own_bound() -> None:
    ieee, transport = make(b"1\n")
    ieee.wait_operation_complete(30.0)
    assert transport.operations[-1].timeout_s == 30.0


def test_wait_operation_complete_translates_a_timeout() -> None:
    """A completion wait that expires is an operation timeout, not just I/O."""
    ieee, transport = make()
    transport.fail_next_read(TransportTimeoutError("no reply"), fault=False)
    with pytest.raises(OperationTimeoutError) as caught:
        ieee.wait_operation_complete(0.5)
    assert isinstance(caught.value.__cause__, TransportTimeoutError)
    assert "0.5" in str(caught.value)


def test_wait_operation_complete_rejects_a_non_completion_reply() -> None:
    ieee, _ = make(b"0\n")
    with pytest.raises(OperationTimeoutError):
        ieee.wait_operation_complete(1.0)


def test_wait_operation_complete_rejects_garbage() -> None:
    ieee, _ = make(b"soon\n")
    with pytest.raises(ResponseParseError):
        ieee.wait_operation_complete(1.0)


# -- diagnostics ----------------------------------------------------------


def test_self_test_pass() -> None:
    ieee, transport = make(b"0\n")
    result = ieee.self_test()
    assert transport.written == b"*TST?\n"
    assert result.passed is True
    assert result.code == 0
    assert result.raw == "0"


def test_self_test_failure_is_reported_not_raised() -> None:
    """Whether a failed self-test fails the run is the caller's policy."""
    ieee, _ = make(b"1\n")
    result = ieee.self_test()
    assert result.passed is False
    assert result.code == 1


def test_self_test_accepts_a_long_bound() -> None:
    ieee, transport = make(b"0\n")
    ieee.self_test(timeout_s=120.0)
    assert transport.operations[-1].timeout_s == 120.0


def test_read_status_byte() -> None:
    ieee, transport = make(b"64\n")
    assert ieee.read_status_byte() == 64
    assert transport.written == b"*STB?\n"


def test_read_event_status() -> None:
    ieee, transport = make(b"32\n")
    assert ieee.read_event_status() == 32
    assert transport.written == b"*ESR?\n"


@pytest.mark.parametrize("method", ["read_status_byte", "read_event_status"])
def test_status_registers_reject_non_integers(method: str) -> None:
    ieee, _ = make(b"nonsense\n")
    with pytest.raises(ResponseParseError):
        getattr(ieee, method)()


def test_status_registers_accept_the_exponential_form() -> None:
    """Some instruments answer integer queries in scientific notation."""
    ieee, _ = make(b"+6.40000000E+01\n")
    assert ieee.read_status_byte() == 64


# -- wiring ---------------------------------------------------------------


def test_client_is_exposed() -> None:
    transport = MockTransport()
    client = ScpiClient(transport)
    assert Ieee4882(client).client is client


def test_nothing_is_sent_on_construction() -> None:
    """Constructing the helper must not talk to the instrument."""
    transport = MockTransport()
    transport.open()
    Ieee4882(ScpiClient(transport))
    assert transport.written == b""
