"""Waiting out a slow command without losing the session.

The N83624 can take a long time over a command. A poll issued while it is busy
may get no answer, and a query whose reply never arrived costs the connection:
the reply may still turn up, and would be read as the answer to whatever is
asked next. These tests pin the behaviour that makes that survivable — the poll
is reported as "not finished", the transport is reopened, and the wait ends at
its own deadline rather than by raising.
"""

from __future__ import annotations

import pytest

from py_ngi_n83624 import ChannelLimits, DriverSafetyPolicy, InstrumentLimits, N83624CellSimulator
from py_ngi_n83624.emulator import SimpleN83624Emulator
from py_ngi_n83624.exceptions import CommunicationError, SessionStateError, TimeoutError


class BusyInstrument(SimpleN83624Emulator):
    """Answers ``*OPC?`` with a timeout until it has been asked often enough.

    ``failures`` polls raise, standing in for an instrument too busy to reply;
    every later poll reports completion.
    """

    def __init__(self, failures: int, *, error: Exception | None = None) -> None:
        super().__init__()
        self.failures = failures
        self.error = error or TimeoutError("no reply from a busy instrument")
        self.opc_polls = 0
        self.opens = 0
        self.closes = 0

    def open(self) -> None:
        self.opens += 1
        super().open()

    def close(self) -> None:
        self.closes += 1
        super().close()

    def query(self, command: str) -> str:
        if command == "*OPC?":
            self.opc_polls += 1
            if self.opc_polls <= self.failures:
                raise self.error
            return "1"
        return super().query(command)


class FakeTime:
    """Stands in for the driver's ``time`` module.

    The clock only advances when something sleeps on it, so these tests run
    instantly and assert on the poll schedule rather than on wall-clock timing.
    """

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture()
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeTime:
    fake = FakeTime()
    monkeypatch.setattr("py_ngi_n83624.driver.time", fake)
    return fake


def limits() -> InstrumentLimits:
    return InstrumentLimits(
        default_channel_limits=ChannelLimits(max_voltage_v=5.0, max_current_ma=1000.0)
    )


def make(transport: SimpleN83624Emulator) -> N83624CellSimulator:
    driver = N83624CellSimulator(
        transport,
        limits=limits(),
        safety_policy=DriverSafetyPolicy(
            require_identity_check_on_connect=False,
            require_status_check_after_setters=False,
            require_interlock_for_output_on=False,
        ),
    )
    driver.connect()
    return driver


def test_a_prompt_instrument_is_not_slept_on(clock: FakeTime) -> None:
    transport = BusyInstrument(failures=0)
    driver = make(transport)
    assert driver.wait_operation_complete(timeout=60.0) is True
    assert transport.opc_polls == 1
    assert clock.slept == []


def test_polls_that_time_out_do_not_end_the_wait(clock: FakeTime) -> None:
    """The behaviour being asked for: a busy instrument is waited out."""
    transport = BusyInstrument(failures=3)
    driver = make(transport)
    assert driver.wait_operation_complete(timeout=600.0) is True
    assert transport.opc_polls == 4


def test_the_transport_is_reopened_after_a_poll_that_got_no_answer(clock: FakeTime) -> None:
    """Without this the next poll would talk over a connection that has faulted."""
    transport = BusyInstrument(failures=2)
    driver = make(transport)
    opens_before = transport.opens
    driver.wait_operation_complete(timeout=600.0)
    assert transport.opens - opens_before == 2
    assert transport.closes == 2
    assert transport.is_open()


def test_reconnecting_can_be_declined(clock: FakeTime) -> None:
    transport = BusyInstrument(failures=2)
    driver = make(transport)
    opens_before = transport.opens
    assert driver.wait_operation_complete(timeout=600.0, reconnect_on_timeout=False) is True
    assert transport.opens == opens_before


def test_a_communication_error_is_treated_the_same_way(clock: FakeTime) -> None:
    """A faulted link surfaces as CommunicationError, not always as a timeout."""
    transport = BusyInstrument(failures=2, error=CommunicationError("transport is not open"))
    driver = make(transport)
    assert driver.wait_operation_complete(timeout=600.0) is True


def test_an_operation_that_never_finishes_is_reported_not_raised(clock: FakeTime) -> None:
    """"Don't crash" means exactly this: a bounded wait that returns False."""
    transport = BusyInstrument(failures=10_000)
    driver = make(transport)
    assert driver.wait_operation_complete(timeout=5.0) is False
    assert clock.now <= 5.0  # never sleeps past its own deadline
    assert driver.transport.is_open()  # and the session is still usable


def test_the_poll_interval_backs_off(clock: FakeTime) -> None:
    """A slow operation must not be polled hundreds of times."""
    transport = BusyInstrument(failures=6)
    driver = make(transport)
    driver.wait_operation_complete(
        timeout=600.0, poll_interval=0.1, backoff=2.0, maximum_poll_interval=0.5
    )
    assert clock.slept == [0.1, 0.2, 0.4, 0.5, 0.5, 0.5]


def test_the_interval_can_be_held_constant(clock: FakeTime) -> None:
    transport = BusyInstrument(failures=3)
    driver = make(transport)
    driver.wait_operation_complete(timeout=600.0, poll_interval=0.25, backoff=1.0)
    assert clock.slept == [0.25, 0.25, 0.25]


def test_a_disconnected_session_is_refused_immediately(clock: FakeTime) -> None:
    """Otherwise a caller's mistake would look like a slow instrument."""
    transport = BusyInstrument(failures=0)
    driver = make(transport)
    driver.transport.close()
    with pytest.raises(SessionStateError):
        driver.wait_operation_complete(timeout=60.0)
    assert transport.opc_polls == 0


def test_a_link_that_cannot_be_reopened_still_ends_at_the_deadline(clock: FakeTime) -> None:
    """A failure inside recovery must not replace the caller's answer."""

    class Unreopenable(BusyInstrument):
        def open(self) -> None:
            if self.opens:
                self.opens += 1
                raise CommunicationError("cannot reopen")
            super().open()

    transport = Unreopenable(failures=10_000)
    driver = make(transport)
    assert driver.wait_operation_complete(timeout=1.0, poll_interval=0.25, backoff=1.0) is False


def test_a_wait_without_a_bound_still_returns(clock: FakeTime) -> None:
    """timeout=None waits indefinitely, which is only safe if it can finish."""
    transport = BusyInstrument(failures=2)
    driver = make(transport)
    assert driver.wait_operation_complete(timeout=None) is True
