from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    ResponseParseError,
    ScpiErrorQueueError,
    TransportError,
)
from scpi_driver_core.execution.retry import RetryPolicy
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.scpi.errors import ScpiErrorQueue, ScpiExecutionPolicy
from scpi_driver_core.transport import MockTransport, ReplayPolicy

NO_ERROR = b'0,"No error"\n'


def make(*replies: bytes) -> tuple[ScpiClient, MockTransport]:
    transport = MockTransport()
    transport.open()
    for reply in replies:
        transport.feed(reply)
    return ScpiClient(transport), transport


# -- configuration --------------------------------------------------------


def test_defaults() -> None:
    client, _ = make()
    queue = ScpiErrorQueue(client)
    assert queue.command == "SYST:ERR?"
    assert queue.no_error_codes == frozenset({0})


def test_command_is_configurable() -> None:
    client, transport = make(NO_ERROR)
    ScpiErrorQueue(client, command="SYSTEM:ERROR:NEXT?").drain()
    assert transport.written == b"SYSTEM:ERROR:NEXT?\n"


def test_no_error_codes_are_configurable() -> None:
    """Some instruments answer with a code other than zero for 'queue empty'."""
    client, _ = make(b'-800,"Queue empty"\n')
    queue = ScpiErrorQueue(client, no_error_codes=frozenset({0, -800}))
    assert queue.drain() == []


@pytest.mark.parametrize(
    "kwargs",
    [{"command": ""}, {"no_error_codes": frozenset()}, {"maximum_entries": 0}],
)
def test_rejects_invalid_configuration(kwargs: dict[str, object]) -> None:
    client, _ = make()
    with pytest.raises(ConfigurationError):
        ScpiErrorQueue(client, **kwargs)  # type: ignore[arg-type]


# -- reading --------------------------------------------------------------


def test_read_one_returns_a_no_error_entry_rather_than_hiding_it() -> None:
    client, _ = make(NO_ERROR)
    entry = ScpiErrorQueue(client).read_one()
    assert entry.code == 0
    assert entry.message == "No error"
    assert entry.raw == '0,"No error"'


def test_read_one_parses_a_real_error() -> None:
    client, _ = make(b'-113,"Undefined header"\n')
    entry = ScpiErrorQueue(client).read_one()
    assert entry.code == -113
    assert entry.message == "Undefined header"


def test_read_one_rejects_a_malformed_reply() -> None:
    client, _ = make(b"gibberish\n")
    with pytest.raises(ResponseParseError):
        ScpiErrorQueue(client).read_one()


def test_is_no_error_uses_the_configured_set() -> None:
    client, _ = make()
    queue = ScpiErrorQueue(client, no_error_codes=frozenset({0, -800}))
    entry = type("E", (), {"code": -800})()
    assert queue.is_no_error(entry) is True  # type: ignore[arg-type]


# -- draining -------------------------------------------------------------


def test_drain_of_an_empty_queue() -> None:
    client, transport = make(NO_ERROR)
    assert ScpiErrorQueue(client).drain() == []
    assert transport.written == b"SYST:ERR?\n"


def test_drain_collects_until_empty() -> None:
    client, transport = make(b'-113,"Undefined header"\n', b'-222,"Data out of range"\n', NO_ERROR)
    errors = ScpiErrorQueue(client).drain()
    assert [error.code for error in errors] == [-113, -222]
    assert transport.written == b"SYST:ERR?\n" * 3


def test_drain_excludes_the_terminating_entry() -> None:
    client, _ = make(b'-113,"Undefined header"\n', NO_ERROR)
    assert len(ScpiErrorQueue(client).drain()) == 1


def test_drain_retains_the_raw_reply() -> None:
    client, _ = make(b'-113,"Undefined header"\n', NO_ERROR)
    assert ScpiErrorQueue(client).drain()[0].raw == '-113,"Undefined header"'


def test_drain_is_bounded_when_the_queue_never_empties() -> None:
    """A device stuck reporting errors must not loop forever."""
    client, transport = make(*[b'-113,"Undefined header"\n'] * 50)
    with pytest.raises(ScpiErrorQueueError, match="did not empty"):
        ScpiErrorQueue(client, maximum_entries=4).drain()
    assert transport.written == b"SYST:ERR?\n" * 4


def test_drain_bound_can_be_overridden_per_call() -> None:
    client, transport = make(*[b'-113,"x"\n'] * 10)
    with pytest.raises(ScpiErrorQueueError):
        ScpiErrorQueue(client).drain(max_entries=2)
    assert transport.written == b"SYST:ERR?\n" * 2


def test_drain_rejects_a_nonpositive_bound() -> None:
    client, _ = make()
    with pytest.raises(ConfigurationError):
        ScpiErrorQueue(client).drain(max_entries=0)


# -- raise_if_errors ------------------------------------------------------


def test_raise_if_errors_is_silent_when_clean() -> None:
    client, _ = make(NO_ERROR)
    ScpiErrorQueue(client).raise_if_errors()


def test_raise_if_errors_lists_every_error() -> None:
    client, _ = make(b'-113,"Undefined header"\n', b'-222,"Data out of range"\n', NO_ERROR)
    with pytest.raises(ScpiErrorQueueError) as caught:
        ScpiErrorQueue(client).raise_if_errors()
    message = str(caught.value)
    assert "2 errors" in message
    assert "-113: Undefined header" in message
    assert "-222: Data out of range" in message


def test_raise_if_errors_uses_the_singular_for_one() -> None:
    client, _ = make(b'-113,"Undefined header"\n', NO_ERROR)
    with pytest.raises(ScpiErrorQueueError, match="1 error:"):
        ScpiErrorQueue(client).raise_if_errors()


# -- execution policy -----------------------------------------------------


def test_policy_defaults_to_checking_nothing() -> None:
    policy = ScpiExecutionPolicy()
    assert policy.check_error_queue_after_write is False
    assert policy.check_error_queue_after_query is False
    assert policy.checks_anything is False


def test_client_does_not_drain_the_queue_unless_enabled() -> None:
    """The core must never consume errors a driver may want to inspect."""
    client, transport = make(b"1.5\n")
    client.query("MEAS?")
    assert transport.written == b"MEAS?\n"


def test_write_checking_runs_after_a_write() -> None:
    client, transport = make(NO_ERROR)
    client.enable_error_checking(
        ScpiErrorQueue(client), ScpiExecutionPolicy(check_error_queue_after_write=True)
    )
    client.write("VOLT 1")
    assert transport.written == b"VOLT 1\nSYST:ERR?\n"


def test_write_checking_raises_on_a_reported_error() -> None:
    client, _ = make(b'-113,"Undefined header"\n', NO_ERROR)
    client.enable_error_checking(
        ScpiErrorQueue(client), ScpiExecutionPolicy(check_error_queue_after_write=True)
    )
    with pytest.raises(ScpiErrorQueueError):
        client.write("BOGUS")


def test_query_checking_runs_after_a_query() -> None:
    client, transport = make(b"1.5\n", NO_ERROR)
    client.enable_error_checking(
        ScpiErrorQueue(client), ScpiExecutionPolicy(check_error_queue_after_query=True)
    )
    assert client.query_float("MEAS?") == 1.5
    assert transport.written == b"MEAS?\nSYST:ERR?\n"


def test_write_checking_does_not_fire_after_a_query() -> None:
    client, transport = make(b"1.5\n")
    client.enable_error_checking(
        ScpiErrorQueue(client), ScpiExecutionPolicy(check_error_queue_after_write=True)
    )
    client.query("MEAS?")
    assert transport.written == b"MEAS?\n"


def test_the_check_does_not_trigger_another_check() -> None:
    """The queue's own queries are exempt, or the check would recurse forever."""
    client, transport = make(NO_ERROR)
    client.enable_error_checking(
        ScpiErrorQueue(client),
        ScpiExecutionPolicy(check_error_queue_after_write=True, check_error_queue_after_query=True),
    )
    client.write("VOLT 1")
    assert transport.written == b"VOLT 1\nSYST:ERR?\n"


def test_checking_can_be_turned_back_off() -> None:
    client, transport = make(NO_ERROR, b"1.5\n")
    queue = ScpiErrorQueue(client)
    client.enable_error_checking(queue, ScpiExecutionPolicy(check_error_queue_after_write=True))
    client.write("VOLT 1")
    client.disable_error_checking()
    client.write("VOLT 2")
    assert client.error_queue is None
    assert transport.written == b"VOLT 1\nSYST:ERR?\nVOLT 2\n"


def test_policy_and_queue_are_visible() -> None:
    client, _ = make()
    queue = ScpiErrorQueue(client)
    policy = ScpiExecutionPolicy(check_error_queue_after_query=True)
    client.enable_error_checking(queue, policy)
    assert client.error_queue is queue
    assert client.execution_policy is policy


# -- retry on the client --------------------------------------------------


def test_query_retry_requires_an_explicit_safe_classification() -> None:
    """Retrying resends a command that may already have reached the device."""
    client, _ = make(b"1.5\n")
    with pytest.raises(ConfigurationError, match="ReplayPolicy.SAFE"):
        client.query("MEAS?", retry_policy=RetryPolicy(attempts=3))


def test_query_retry_is_allowed_when_classified_safe() -> None:
    client, transport = make(b"1.5\n")
    transport.fail_next_read(TransportError("glitch"), fault=False)
    result = client.query(
        "MEAS?", replay_policy=ReplayPolicy.SAFE, retry_policy=RetryPolicy(attempts=2)
    )
    assert result == "1.5"


def test_a_single_attempt_policy_needs_no_safe_classification() -> None:
    client, _ = make(b"1.5\n")
    assert client.query("MEAS?", retry_policy=RetryPolicy(attempts=1)) == "1.5"


def test_retry_attempts_reach_the_observer() -> None:
    transport = MockTransport()
    transport.open()
    transport.feed(b"1.5\n")
    seen = []
    client = ScpiClient(transport, retry_observer=seen.append)
    transport.fail_next_read(TransportError("glitch"), fault=False)
    client.query("MEAS?", replay_policy=ReplayPolicy.SAFE, retry_policy=RetryPolicy(attempts=2))
    assert [attempt.number for attempt in seen] == [1, 2]
