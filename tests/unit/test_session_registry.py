from __future__ import annotations

import pytest

from scpi_driver_core.exceptions import ConfigurationError, TransportError
from scpi_driver_core.scpi import ScpiClient
from scpi_driver_core.session.registry import (
    DEFAULT_ALIAS,
    SessionRegistry,
    normalize_alias,
)
from scpi_driver_core.session.session import ScpiSession
from scpi_driver_core.transport import MockTransport


def session(alias: str = DEFAULT_ALIAS) -> ScpiSession:
    return ScpiSession(alias, ScpiClient(MockTransport()))


def opened(alias: str = DEFAULT_ALIAS) -> ScpiSession:
    made = session(alias)
    made.open()
    return made


# -- alias normalization --------------------------------------------------


@pytest.mark.parametrize(
    ("given", "expected"),
    [("PSU", "psu"), ("  psu  ", "psu"), ("PsU", "psu"), ("PSU 1", "psu 1")],
)
def test_normalize_alias(given: str, expected: str) -> None:
    assert normalize_alias(given) == expected


@pytest.mark.parametrize("given", ["", "   ", "\t"])
def test_normalize_alias_rejects_empty(given: str) -> None:
    with pytest.raises(ConfigurationError, match="alias"):
        normalize_alias(given)


def test_aliases_differing_only_in_case_are_the_same_session() -> None:
    """Otherwise two aliases would silently shadow each other."""
    registry = SessionRegistry()
    first = session()
    registry.register("PSU", first)
    assert registry.get("psu") is first
    assert "  PsU " in registry


# -- registration ---------------------------------------------------------


def test_register_and_get() -> None:
    registry = SessionRegistry()
    made = session()
    registry.register(DEFAULT_ALIAS, made)
    assert registry.get(DEFAULT_ALIAS) is made
    assert len(registry) == 1


def test_default_alias_is_deterministic() -> None:
    registry = SessionRegistry()
    registry.register(DEFAULT_ALIAS, session())
    assert registry.list_aliases() == ["default"]


def test_duplicate_registration_is_rejected() -> None:
    """Silently replacing would strand the previous transport, still open."""
    registry = SessionRegistry()
    registry.register("psu", session())
    with pytest.raises(ConfigurationError, match="already registered"):
        registry.register("psu", session())


def test_duplicate_can_be_replaced_deliberately() -> None:
    registry = SessionRegistry()
    registry.register("psu", session())
    replacement = session()
    registry.register("psu", replacement, replace=True)
    assert registry.get("psu") is replacement
    assert len(registry) == 1


def test_get_unknown_alias_lists_what_is_available() -> None:
    registry = SessionRegistry()
    registry.register("psu", session())
    with pytest.raises(ConfigurationError, match="psu") as caught:
        registry.get("scope")
    assert "no session registered" in str(caught.value)


def test_contains_and_len_on_an_empty_registry() -> None:
    registry = SessionRegistry()
    assert len(registry) == 0
    assert "psu" not in registry


# -- the active session ---------------------------------------------------


def test_first_registration_becomes_active() -> None:
    registry = SessionRegistry()
    first = session()
    registry.register("psu", first)
    assert registry.get_active() is first
    assert registry.active_alias == "psu"


def test_later_registrations_do_not_steal_active() -> None:
    registry = SessionRegistry()
    first = session()
    registry.register("psu", first)
    registry.register("scope", session())
    assert registry.get_active() is first


def test_set_active_switches() -> None:
    registry = SessionRegistry()
    registry.register("psu", session())
    scope = session()
    registry.register("scope", scope)
    registry.set_active("SCOPE")
    assert registry.get_active() is scope
    assert registry.active_alias == "scope"


def test_set_active_rejects_an_unknown_alias() -> None:
    registry = SessionRegistry()
    registry.register("psu", session())
    with pytest.raises(ConfigurationError):
        registry.set_active("scope")


def test_get_active_on_an_empty_registry() -> None:
    with pytest.raises(ConfigurationError, match="no sessions"):
        SessionRegistry().get_active()


def test_removing_the_active_session_does_not_promote_a_survivor() -> None:
    """Picking an instrument the caller did not choose could energize the wrong bench."""
    registry = SessionRegistry()
    registry.register("psu", session())
    registry.register("scope", session())
    registry.remove("psu")
    with pytest.raises(ConfigurationError, match="no active session"):
        registry.get_active()


def test_the_error_says_how_to_recover() -> None:
    registry = SessionRegistry()
    registry.register("psu", session())
    registry.register("scope", session())
    registry.remove("psu")
    with pytest.raises(ConfigurationError, match="scope"):
        registry.get_active()


def test_active_can_be_chosen_again_after_removal() -> None:
    registry = SessionRegistry()
    registry.register("psu", session())
    scope = session()
    registry.register("scope", scope)
    registry.remove("psu")
    registry.set_active("scope")
    assert registry.get_active() is scope


# -- listing --------------------------------------------------------------


def test_listing_is_sorted_and_reproducible() -> None:
    registry = SessionRegistry()
    for alias in ("scope", "psu", "dmm"):
        registry.register(alias, session(alias))
    assert registry.list_aliases() == ["dmm", "psu", "scope"]
    assert [s.alias for s in registry.list_sessions()] == ["dmm", "psu", "scope"]


def test_listing_an_empty_registry() -> None:
    registry = SessionRegistry()
    assert registry.list_aliases() == []
    assert registry.list_sessions() == []


# -- removal and disconnection --------------------------------------------


def test_remove_returns_the_session_without_closing_it() -> None:
    registry = SessionRegistry()
    made = opened("psu")
    registry.register("psu", made)
    assert registry.remove("psu") is made
    assert made.is_connected is True


def test_remove_rejects_an_unknown_alias() -> None:
    with pytest.raises(ConfigurationError):
        SessionRegistry().remove("psu")


def test_disconnect_closes_and_unregisters() -> None:
    registry = SessionRegistry()
    made = opened("psu")
    registry.register("psu", made)
    registry.disconnect("psu")
    assert made.is_connected is False
    assert len(registry) == 0


def test_disconnect_all_closes_everything() -> None:
    registry = SessionRegistry()
    sessions = [opened(alias) for alias in ("psu", "scope", "dmm")]
    for made in sessions:
        registry.register(made.alias, made)
    registry.disconnect_all()
    assert all(not made.is_connected for made in sessions)
    assert len(registry) == 0
    assert registry.active_alias is None


def test_disconnect_all_on_an_empty_registry() -> None:
    SessionRegistry().disconnect_all()


def test_disconnect_all_closes_the_rest_when_one_fails() -> None:
    """One stuck instrument must not leave the remaining bench connected."""
    registry = SessionRegistry()
    stuck = opened("psu")
    healthy = opened("scope")

    def boom() -> None:
        raise TransportError("stuck")

    stuck.transport.close = boom  # type: ignore[method-assign]
    registry.register("psu", stuck)
    registry.register("scope", healthy)

    with pytest.raises(TransportError, match="stuck"):
        registry.disconnect_all()
    assert healthy.is_connected is False
    assert len(registry) == 0


def test_disconnect_unregisters_even_if_closing_fails() -> None:
    registry = SessionRegistry()
    made = opened("psu")

    def boom() -> None:
        raise TransportError("stuck")

    made.transport.close = boom  # type: ignore[method-assign]
    registry.register("psu", made)
    with pytest.raises(TransportError):
        registry.disconnect("psu")
    assert "psu" not in registry


def test_removing_a_non_active_session_leaves_active_alone() -> None:
    registry = SessionRegistry()
    first = session()
    registry.register("psu", first)
    registry.register("scope", session())
    registry.remove("scope")
    assert registry.get_active() is first
    assert registry.active_alias == "psu"


def test_disconnect_all_raises_the_first_failure_of_several() -> None:
    registry = SessionRegistry()
    first_failing = opened("a")
    second_failing = opened("b")

    def first_boom() -> None:
        raise TransportError("first stuck")

    def second_boom() -> None:
        raise TransportError("second stuck")

    first_failing.transport.close = first_boom  # type: ignore[method-assign]
    second_failing.transport.close = second_boom  # type: ignore[method-assign]
    registry.register("a", first_failing)
    registry.register("b", second_failing)

    with pytest.raises(TransportError, match="first stuck"):
        registry.disconnect_all()
    assert len(registry) == 0
