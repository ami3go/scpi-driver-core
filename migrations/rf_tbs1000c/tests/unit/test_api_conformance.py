"""Automatic validation of this driver's whole public surface.

Written per driver but driven by the shared harness in
``migrations/driver_api_conformance.py``, so every migrated driver is held to
the same standard without a copy of the logic in each package.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The harness lives alongside the other migrated drivers.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import driver_api_conformance as conformance  # noqa: E402

from tbs1000c.driver import Tbs1000c
from tbs1000c.exceptions import Tbs1000cError  # noqa: E402

SNAPSHOT = Path(__file__).resolve().parent / "api_snapshot.txt"
ANNOTATION_GAPS = Path(__file__).resolve().parent / "api_annotation_gaps.txt"
TOLERATED = (Tbs1000cError, NotImplementedError,)


def make() -> Tbs1000c:
    return Tbs1000c.connect_simulated()


DRIVER = conformance.DriverUnderTest(
    cls=Tbs1000c,
    make=make,
    snapshot=SNAPSHOT,
    annotation_gaps=ANNOTATION_GAPS,
    tolerated=TOLERATED,
)


def test_the_public_surface_is_not_empty() -> None:
    """Guards the harness itself: a silent no-op would pass everything else."""
    assert len(conformance.public_members(Tbs1000c)) > 10


def test_no_new_annotation_gaps() -> None:
    """Existing gaps in this vendored driver are recorded; a new one fails."""
    new = conformance.check_annotation_gaps(DRIVER)
    assert not new, f"newly unannotated public API: {new}"


def test_the_public_surface_matches_the_snapshot() -> None:
    """A rename, removal, or newly undocumented member must be deliberate.

    The snapshot records which members lack a docstring, so pre-existing gaps
    in this vendored driver are tolerated while a new one fails.
    """
    removed, added = conformance.check_snapshot(DRIVER)
    assert not removed, f"public API removed or changed: {removed}"
    assert not added, f"public API added or changed; refresh the snapshot: {added}"


def test_documentation_debt_does_not_grow() -> None:
    """Reported separately so the number is visible rather than buried."""
    recorded = SNAPSHOT.read_text(encoding="utf-8").count("[undocumented]")
    assert len(conformance.undocumented(Tbs1000c)) <= recorded


def test_every_no_argument_method_works_against_the_simulator() -> None:
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
