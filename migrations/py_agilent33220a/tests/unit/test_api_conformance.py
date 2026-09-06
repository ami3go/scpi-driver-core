"""Automatic validation of this driver's whole public surface.

Written per driver but driven by the shared harness in
``migrations/driver_api_conformance.py``, so every migrated driver is held to
the same standard without eight copies of the logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# The harness lives one level up, alongside the other migrated drivers.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import driver_api_conformance as conformance  # noqa: E402

from py_agilent33220a.driver import Agilent33220A  # noqa: E402
from py_agilent33220a.exceptions import Agilent33220AError  # noqa: E402

SNAPSHOT = Path(__file__).resolve().parent / "api_snapshot.txt"
ANNOTATION_GAPS = Path(__file__).resolve().parent / "api_annotation_gaps.txt"


def make() -> Agilent33220A:
    return Agilent33220A.connect_simulated()


DRIVER = conformance.DriverUnderTest(
    cls=Agilent33220A,
    make=make,
    snapshot=SNAPSHOT,
    annotation_gaps=ANNOTATION_GAPS,
    tolerated=(Agilent33220AError, NotImplementedError),
)


def test_the_public_surface_is_not_empty() -> None:
    """Guards the harness itself: a silent no-op would pass everything else."""
    assert len(conformance.public_members(Agilent33220A)) > 50


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
    assert len(conformance.undocumented(Agilent33220A)) <= recorded


def test_every_no_argument_method_works_against_the_simulator() -> None:
    """The check that would catch a migration breaking a method."""
    failures = conformance.sweep(DRIVER)
    assert not failures, f"methods failed unexpectedly: {failures}"


def test_every_public_property_is_readable() -> None:
    failures = conformance.read_properties(DRIVER)
    assert not failures, f"properties failed unexpectedly: {failures}"


def test_the_sweep_actually_covers_a_useful_number_of_methods() -> None:
    """Otherwise an over-broad exclusion list could make the sweep vacuous."""
    swept = conformance.invocable_without_arguments(DRIVER)
    assert len(swept) >= 20, f"sweep only covers {len(swept)} methods: {swept}"


@pytest.mark.parametrize(
    "name", sorted(conformance.invocable_without_arguments(DRIVER))
)
def test_method_is_individually_invocable(name: str) -> None:
    """Reported per method, so a failure names the culprit directly."""
    instance = make()
    try:
        getattr(instance, name)()
    except (Agilent33220AError, NotImplementedError):
        pass  # the driver answered in its own vocabulary
    finally:
        instance.close()
