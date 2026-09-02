from __future__ import annotations

import dataclasses

import pytest

from scpi_driver_core.exceptions import ConfigurationError
from scpi_driver_core.transport import (
    FlushDirection,
    ReadMode,
    ReadRequest,
    ReplayPolicy,
    TransportDescriptor,
    TransportState,
    WriteResult,
)


def test_transport_state_members() -> None:
    assert {state.name for state in TransportState} == {
        "CREATED",
        "OPENING",
        "OPEN",
        "FAULTED",
        "CLOSING",
        "CLOSED",
    }


def test_read_mode_members() -> None:
    assert {mode.name for mode in ReadMode} == {
        "UNTIL_TERMINATOR",
        "EXACT_LENGTH",
        "UP_TO_LENGTH",
        "AVAILABLE",
        "BACKEND_DEFINED_MESSAGE",
    }


def test_flush_direction_members() -> None:
    assert {direction.name for direction in FlushDirection} == {
        "INPUT",
        "OUTPUT",
        "BOTH",
    }


def test_replay_policy_members() -> None:
    assert {policy.name for policy in ReplayPolicy} == {"NEVER", "SAFE"}


def test_descriptor_equality_and_immutability() -> None:
    first = TransportDescriptor(kind="tcp", address="192.0.2.10:5025")
    second = TransportDescriptor(kind="tcp", address="192.0.2.10:5025")
    assert first == second
    assert first.metadata == {}
    with pytest.raises(dataclasses.FrozenInstanceError):
        first.kind = "udp"  # type: ignore[misc]


def test_descriptor_metadata_is_not_shared_between_instances() -> None:
    first = TransportDescriptor(kind="visa", address="GPIB0::22::INSTR")
    second = TransportDescriptor(
        kind="visa", address="GPIB0::23::INSTR", metadata={"backend": "@py"}
    )
    assert first.metadata == {}
    assert second.metadata == {"backend": "@py"}


def test_read_request_defaults() -> None:
    request = ReadRequest(mode=ReadMode.AVAILABLE)
    assert request.length is None
    assert request.terminator is None
    assert request.include_terminator is False
    assert request.maximum_size == 1_048_576


def test_read_request_until_terminator() -> None:
    request = ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n")
    assert request.terminator == b"\n"


@pytest.mark.parametrize("mode", [ReadMode.EXACT_LENGTH, ReadMode.UP_TO_LENGTH])
def test_read_request_length_modes_accept_positive_length(mode: ReadMode) -> None:
    assert ReadRequest(mode=mode, length=16).length == 16


@pytest.mark.parametrize("mode", [ReadMode.EXACT_LENGTH, ReadMode.UP_TO_LENGTH])
@pytest.mark.parametrize("length", [None, 0, -1])
def test_read_request_length_modes_reject_missing_length(
    mode: ReadMode, length: int | None
) -> None:
    with pytest.raises(ConfigurationError):
        ReadRequest(mode=mode, length=length)


def test_read_request_rejects_length_above_maximum_size() -> None:
    with pytest.raises(ConfigurationError):
        ReadRequest(mode=ReadMode.EXACT_LENGTH, length=1024, maximum_size=512)


@pytest.mark.parametrize("terminator", [None, b""])
def test_read_request_until_terminator_requires_terminator(
    terminator: bytes | None,
) -> None:
    with pytest.raises(ConfigurationError):
        ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=terminator)


@pytest.mark.parametrize("maximum_size", [0, -1])
def test_read_request_rejects_nonpositive_maximum_size(maximum_size: int) -> None:
    with pytest.raises(ConfigurationError):
        ReadRequest(mode=ReadMode.AVAILABLE, maximum_size=maximum_size)


def test_write_result_equality() -> None:
    assert WriteResult(bytes_written=7) == WriteResult(bytes_written=7)
    assert WriteResult(bytes_written=7) != WriteResult(bytes_written=8)
