from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.execution import RetryPolicy
from scpi_driver_core.transport import ReadMode, ReadRequest

pytestmark = pytest.mark.property


@given(
    length=st.integers(min_value=1, max_value=65_536),
    slack=st.integers(min_value=0, max_value=65_536),
)
def test_length_read_requests_accept_every_bounded_valid_shape(length: int, slack: int) -> None:
    maximum_size = length + slack

    for mode in (ReadMode.EXACT_LENGTH, ReadMode.UP_TO_LENGTH):
        request = ReadRequest(mode=mode, length=length, maximum_size=maximum_size)
        assert request.length == length
        assert request.maximum_size == maximum_size


@given(length=st.integers(min_value=2, max_value=65_536))
def test_length_read_requests_reject_length_above_bound(length: int) -> None:
    with pytest.raises(ConfigurationError):
        ReadRequest(mode=ReadMode.EXACT_LENGTH, length=length, maximum_size=length - 1)


@given(
    attempts=st.integers(min_value=2, max_value=20),
    initial_delay_s=st.floats(
        min_value=0.0,
        max_value=10.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    backoff=st.floats(
        min_value=0.1,
        max_value=4.0,
        allow_nan=False,
        allow_infinity=False,
    ),
    fast_attempts=st.integers(min_value=0, max_value=10),
    max_delay_s=st.floats(
        min_value=0.01,
        max_value=20.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_retry_schedule_is_finite_non_negative_and_capped(
    attempts: int,
    initial_delay_s: float,
    backoff: float,
    fast_attempts: int,
    max_delay_s: float,
) -> None:
    policy = RetryPolicy(
        attempts=attempts,
        initial_delay_s=initial_delay_s,
        backoff=backoff,
        fast_attempts=fast_attempts,
        max_delay_s=max_delay_s,
    )

    delays = [policy.delay_before(attempt) for attempt in range(1, attempts + 1)]

    assert delays[0] == 0.0
    assert delays[1] == min(initial_delay_s, max_delay_s)
    assert all(math.isfinite(delay) and delay >= 0 for delay in delays)
    assert all(delay <= max_delay_s for delay in delays)


@given(
    attempts=st.integers(min_value=2, max_value=20),
    delay_s=st.floats(
        min_value=0.0,
        max_value=10.0,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_constant_retry_policy_keeps_one_delay(attempts: int, delay_s: float) -> None:
    policy = RetryPolicy.constant(attempts=attempts, delay_s=delay_s)

    assert [policy.delay_before(attempt) for attempt in range(2, attempts + 1)] == [delay_s] * (
        attempts - 1
    )
