from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import (
    ConfigurationError,
    IdentityError,
    NotConnectedError,
    OperationTimeoutError,
    ProtocolError,
    ResponseParseError,
    SafetyGuardError,
    ScpiCommandError,
    ScpiDriverError,
    ScpiErrorQueueError,
    TransportError,
    TransportTimeoutError,
    UnsupportedOperationError,
)

HIERARCHY = [
    (ConfigurationError, ScpiDriverError),
    (TransportError, ScpiDriverError),
    (NotConnectedError, TransportError),
    (TransportTimeoutError, TransportError),
    (ProtocolError, ScpiDriverError),
    (ResponseParseError, ProtocolError),
    (ScpiCommandError, ProtocolError),
    (ScpiErrorQueueError, ScpiDriverError),
    (IdentityError, ScpiDriverError),
    (OperationTimeoutError, ScpiDriverError),
    (UnsupportedOperationError, ScpiDriverError),
    (SafetyGuardError, ScpiDriverError),
]


@pytest.mark.parametrize(("child", "parent"), HIERARCHY)
def test_parent_relationship(child: type[ScpiDriverError], parent: type[ScpiDriverError]) -> None:
    assert issubclass(child, parent)


@pytest.mark.parametrize(("child", "parent"), HIERARCHY)
def test_raisable_and_catchable_via_parent(
    child: type[ScpiDriverError], parent: type[ScpiDriverError]
) -> None:
    with pytest.raises(parent) as excinfo:
        raise child("boom")
    assert str(excinfo.value) == "boom"


def test_base_is_an_exception() -> None:
    assert issubclass(ScpiDriverError, Exception)


def test_transport_timeout_is_not_an_operation_timeout() -> None:
    assert not issubclass(TransportTimeoutError, OperationTimeoutError)
    assert not issubclass(OperationTimeoutError, TransportError)


def test_chaining_preserves_cause() -> None:
    original = ValueError("backend failed")
    with pytest.raises(TransportError) as excinfo:
        try:
            raise original
        except ValueError as exc:
            raise TransportError("translated") from exc
    assert excinfo.value.__cause__ is original
