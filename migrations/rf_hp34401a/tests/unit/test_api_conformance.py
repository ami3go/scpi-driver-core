"""Automatic validation of this driver's whole public surface.

Driven by the shared harness in ``migrations/driver_api_conformance.py``.

Unlike the other migrated drivers this one has no ``connect_simulated``
classmethod, so the instance is built from its own ``FakeTransport`` with a
default response. Identity verification is turned off in the config because
that fake answers every query the same way and would fail the check for reasons
that have nothing to do with the API surface.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The harness lives alongside the other migrated drivers.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import driver_api_conformance as conformance  # noqa: E402

from hp34401a_dmm import DriverConfig, FakeTransport, Hp34401A  # noqa: E402
from hp34401a_dmm.errors import Hp34401AError  # noqa: E402

SNAPSHOT = Path(__file__).resolve().parent / "api_snapshot.txt"
ANNOTATION_GAPS = Path(__file__).resolve().parent / "api_annotation_gaps.txt"

#: ValueError is tolerated because the fake answers "+1.0" to everything, so a
#: getter expecting an enum or a mode string legitimately rejects it.
TOLERATED = (Hp34401AError, NotImplementedError, ValueError)


def make() -> Hp34401A:
    return Hp34401A(
        FakeTransport(default_response="+1.0"),
        DriverConfig(verify_identity_on_connect=False),
    )


DRIVER = conformance.DriverUnderTest(
    cls=Hp34401A,
    make=make,
    snapshot=SNAPSHOT,
    annotation_gaps=ANNOTATION_GAPS,
    tolerated=TOLERATED,
)


def test_the_public_surface_is_not_empty() -> None:
    """Guards the harness itself: a silent no-op would pass everything else."""
    assert len(conformance.public_members(Hp34401A)) > 10


def test_no_new_annotation_gaps() -> None:
    """Existing gaps in this vendored driver are recorded; a new one fails."""
    new = conformance.check_annotation_gaps(DRIVER)
    assert not new, f"newly unannotated public API: {new}"


def test_the_public_surface_matches_the_snapshot() -> None:
    """A rename, removal, or newly undocumented member must be deliberate."""
    removed, added = conformance.check_snapshot(DRIVER)
    assert not removed, f"public API removed or changed: {removed}"
    assert not added, f"public API added or changed; refresh the snapshot: {added}"


def test_documentation_debt_does_not_grow() -> None:
    """Reported separately so the number is visible rather than buried."""
    recorded = SNAPSHOT.read_text(encoding="utf-8").count("[undocumented]")
    assert len(conformance.undocumented(Hp34401A)) <= recorded


def test_every_no_argument_method_works_against_the_fake_transport() -> None:
    """The check that would catch a migration breaking a method."""
    failures = conformance.sweep(DRIVER)
    assert not failures, f"methods failed unexpectedly: {failures}"


def test_every_public_property_is_readable() -> None:
    failures = conformance.read_properties(DRIVER)
    assert not failures, f"properties failed unexpectedly: {failures}"


@pytest.mark.parametrize("name", sorted(conformance.invocable_without_arguments(DRIVER)))
def test_method_is_individually_invocable(name: str) -> None:
    """Reported per method, so a failure names the culprit directly."""
    instance = make()
    try:
        getattr(instance, name)()
    except TOLERATED:
        pass  # the driver answered in its own vocabulary
    finally:
        conformance._close_quietly(instance)
