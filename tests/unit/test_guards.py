from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import ConfigurationError, SafetyGuardError
from scpi_driver_core.execution.guards import ConfirmationGuard

PHRASE = "ENABLE RAW SCPI"


def test_starts_locked() -> None:
    assert ConfirmationGuard(PHRASE).is_enabled is False


def test_rejects_an_empty_phrase() -> None:
    """An empty phrase would make the guard trivially satisfiable."""
    with pytest.raises(ConfigurationError):
        ConfirmationGuard("")


def test_enable_with_the_right_phrase() -> None:
    guard = ConfirmationGuard(PHRASE)
    guard.enable(PHRASE)
    assert guard.is_enabled is True
    guard.require_enabled()


def test_require_enabled_raises_while_locked() -> None:
    with pytest.raises(SafetyGuardError, match="guarded"):
        ConfirmationGuard(PHRASE).require_enabled()


@pytest.mark.parametrize(
    "attempt",
    ["enable raw scpi", "ENABLE RAW SCPI ", " ENABLE RAW SCPI", "ENABLE  RAW SCPI", "yes", ""],
)
def test_enable_rejects_an_inexact_phrase(attempt: str) -> None:
    guard = ConfirmationGuard(PHRASE)
    with pytest.raises(SafetyGuardError):
        guard.enable(attempt)
    assert guard.is_enabled is False


def test_failed_enable_says_the_phrase_did_not_match() -> None:
    """The phrase is a deliberate-action token, not a credential, so say what went wrong."""
    guard = ConfirmationGuard(PHRASE)
    with pytest.raises(SafetyGuardError, match="did not match"):
        guard.enable("wrong")


def test_disable_relocks() -> None:
    guard = ConfirmationGuard(PHRASE)
    guard.enable(PHRASE)
    guard.disable()
    assert guard.is_enabled is False
    with pytest.raises(SafetyGuardError):
        guard.require_enabled()


def test_disable_is_idempotent() -> None:
    guard = ConfirmationGuard(PHRASE)
    guard.disable()
    guard.disable()
    assert guard.is_enabled is False


def test_name_appears_in_errors() -> None:
    guard = ConfirmationGuard("CALIBRATE NOW", name="calibration")
    with pytest.raises(SafetyGuardError, match="calibration"):
        guard.require_enabled()


def test_name_defaults_to_the_phrase() -> None:
    assert ConfirmationGuard(PHRASE).name == PHRASE


def test_guards_are_independent() -> None:
    """Confirming raw SCPI must not also confirm calibration."""
    raw = ConfirmationGuard(PHRASE)
    calibration = ConfirmationGuard("CALIBRATE NOW")
    raw.enable(PHRASE)
    assert calibration.is_enabled is False
    with pytest.raises(SafetyGuardError):
        calibration.require_enabled()


def test_separate_instances_of_the_same_phrase_do_not_share_state() -> None:
    """State is per instance; there is no ambient authorization."""
    first = ConfirmationGuard(PHRASE)
    second = ConfirmationGuard(PHRASE)
    first.enable(PHRASE)
    assert second.is_enabled is False


def test_scoped_enable_restores_the_previous_state() -> None:
    guard = ConfirmationGuard(PHRASE)
    with guard.enabled(PHRASE):
        guard.require_enabled()
    assert guard.is_enabled is False


def test_scoped_enable_relocks_after_an_exception() -> None:
    guard = ConfirmationGuard(PHRASE)
    with pytest.raises(RuntimeError), guard.enabled(PHRASE):
        raise RuntimeError("operation failed")
    assert guard.is_enabled is False


def test_scoped_enable_keeps_an_already_enabled_guard_enabled() -> None:
    guard = ConfirmationGuard(PHRASE)
    guard.enable(PHRASE)
    with guard.enabled(PHRASE):
        pass
    assert guard.is_enabled is True


def test_scoped_enable_rejects_a_wrong_phrase() -> None:
    guard = ConfirmationGuard(PHRASE)
    with pytest.raises(SafetyGuardError), guard.enabled("wrong"):
        pass  # pragma: no cover - the context manager never yields
    assert guard.is_enabled is False


def test_phrase_is_readable_for_a_driver_that_documents_it() -> None:
    assert ConfirmationGuard(PHRASE).phrase == PHRASE
