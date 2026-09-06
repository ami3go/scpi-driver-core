from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    IdentityError,
    OperationTimeoutError,
    ResponseParseError,
    TransportTimeoutError,
)
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.scpi.ieee488 import OPERATION_COMPLETE_BIT, Ieee4882
from scpi_driver_core.transport import MockTransport, TransportState


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


# -- slow operations: *OPC armed, *ESR? polled ----------------------------


class FakeClock:
    """A monotonic clock that only advances when something sleeps on it.

    Real sleeps would make these tests slow and flaky, and the point being
    tested is the sequence of polls, not wall-clock behaviour.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_wait_for_completion_arms_opc_then_polls_esr() -> None:
    """The sequence that lets a slow operation be waited on without a long read."""
    ieee, transport = make(b"0\n", b"0\n", b"1\n")
    clock = FakeClock()
    result = ieee.wait_for_completion(timeout_s=60.0, clock=clock, sleep=clock.sleep)
    assert transport.written == b"*OPC\n*ESR?\n*ESR?\n*ESR?\n"
    assert result.polls == 3
    assert result.event_status == OPERATION_COMPLETE_BIT


def test_wait_for_completion_returns_at_once_when_already_complete() -> None:
    ieee, transport = make(b"1\n")
    clock = FakeClock()
    ieee.wait_for_completion(timeout_s=60.0, clock=clock, sleep=clock.sleep)
    assert transport.written == b"*OPC\n*ESR?\n"
    assert clock.slept == []


def test_wait_for_completion_can_skip_arming() -> None:
    """For a command that arms the completion bit itself."""
    ieee, transport = make(b"1\n")
    ieee.wait_for_completion(timeout_s=60.0, arm=False)
    assert transport.written == b"*ESR?\n"


def test_the_poll_interval_backs_off() -> None:
    """A fast operation is noticed at once; a slow one is not polled forever."""
    ieee, _ = make(*([b"0\n"] * 5), b"1\n")
    clock = FakeClock()
    ieee.wait_for_completion(
        timeout_s=600.0, interval_s=0.1, backoff=2.0, clock=clock, sleep=clock.sleep
    )
    assert clock.slept == [0.1, 0.2, 0.4, 0.8, 1.0]  # capped by the default maximum


def test_the_interval_can_be_held_constant() -> None:
    ieee, _ = make(b"0\n", b"0\n", b"1\n")
    clock = FakeClock()
    ieee.wait_for_completion(
        timeout_s=60.0, interval_s=0.25, backoff=1.0, clock=clock, sleep=clock.sleep
    )
    assert clock.slept == [0.25, 0.25]


def test_a_wait_that_runs_over_its_deadline_raises_but_leaves_the_link_usable() -> None:
    """The whole point: a timeout here must not cost the connection.

    A long blocking read cannot offer this. Timing one out strands the reply in
    the instrument's output buffer, so the transport has to fault rather than
    risk returning it as the answer to the next query.
    """
    # A 1s bound polled every 0.25s gets exactly five polls: at 0, .25, .5,
    # .75 and 1.0, the last of which finds the deadline spent.
    ieee, transport = make(*([b"0\n"] * 5))
    clock = FakeClock()
    with pytest.raises(OperationTimeoutError, match="not met within 1.0s"):
        ieee.wait_for_completion(
            timeout_s=1.0, interval_s=0.25, backoff=1.0, clock=clock, sleep=clock.sleep
        )
    assert transport.state is TransportState.OPEN
    assert transport.is_open
    # And the client can still be used, which is what "did not crash" means.
    transport.feed(b"1\n")
    assert ieee.operation_complete()


def test_a_status_poll_that_times_out_is_reported_as_a_failed_wait() -> None:
    """*ESR? is answered even by a busy instrument, so this is a real fault."""
    ieee, transport = make()
    transport.fail_next_read(TransportTimeoutError("read timed out"), fault=True)
    with pytest.raises(OperationTimeoutError, match="stopped responding to status polls") as info:
        ieee.wait_for_completion(timeout_s=60.0)
    assert isinstance(info.value.__cause__, TransportTimeoutError)
    assert transport.state is TransportState.FAULTED


def test_error_bits_seen_while_polling_are_not_lost() -> None:
    """*ESR? clears the register, so a bit raised mid-wait is reported once."""
    ieee, _ = make(b"32\n", b"0\n", b"1\n")  # command error, then completion
    clock = FakeClock()
    result = ieee.wait_for_completion(timeout_s=60.0, clock=clock, sleep=clock.sleep)
    assert result.event_status == 0x20 | OPERATION_COMPLETE_BIT


def test_completion_is_detected_alongside_other_bits() -> None:
    ieee, _ = make(b"17\n")  # bit 4 (execution error) and bit 0 together
    result = ieee.wait_for_completion(timeout_s=60.0)
    assert result.polls == 1
    assert result.event_status == 0x11


def test_run_until_complete_sends_the_full_sequence() -> None:
    ieee, transport = make(b"0\n", b"1\n")
    clock = FakeClock()
    ieee.run_until_complete("CALibration:ALL", timeout_s=600.0, clock=clock, sleep=clock.sleep)
    assert transport.written == b"*CLS\nCALibration:ALL\n*OPC\n*ESR?\n*ESR?\n"


def test_run_until_complete_can_leave_the_error_queue_alone() -> None:
    ieee, transport = make(b"1\n")
    ieee.run_until_complete("INITiate", timeout_s=60.0, clear_first=False)
    assert transport.written == b"INITiate\n*OPC\n*ESR?\n"


def test_run_until_complete_reports_a_timeout_with_the_link_intact() -> None:
    ieee, transport = make(*([b"0\n"] * 40))
    clock = FakeClock()
    with pytest.raises(OperationTimeoutError):
        ieee.run_until_complete(
            "SWEep", timeout_s=1.0, interval_s=0.25, backoff=1.0, clock=clock, sleep=clock.sleep
        )
    assert transport.is_open
