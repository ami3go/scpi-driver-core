"""A reusable API-conformance harness for the migrated drivers.

Each driver exposes a large public surface — the 33220A alone has 113 public
methods — and a migration that quietly broke one of them would not be caught by
tests written per feature. This walks the surface instead of enumerating it.

Four things are checked:

1. **Typing, as a ratchet.** Annotation gaps are recorded the same way, for the
   same reason: the vendored drivers are nearly complete but not perfectly so,
   and closing the last gaps is their maintainers' change to make, not a
   migration's.
2. **Stability.** The public surface matches a checked-in snapshot, so a rename
   or removal is a test failure rather than a surprise for a caller.
3. **Documentation, as a ratchet.** The snapshot marks which members lack a
   docstring. Most of these drivers were written without them and adding ninety
   would be the rewrite section 43 forbids during a migration, so existing gaps
   are recorded rather than failed — but a newly undocumented method changes the
   snapshot and fails.
4. **Behaviour.** Every method that takes no required arguments is actually
   invoked against the driver's own simulator, and must not raise anything
   outside the driver's declared exception hierarchy.

Point 4 is the one that catches a broken migration, and it is deliberately
bounded. Only the simulator is ever driven, never a real transport, and
lifecycle methods that would tear the session down or reach for hardware are
excluded by name. Nothing here should ever be pointed at an instrument: a
harness that blindly invokes every method on live hardware would happily enable
an output.

This module lives in ``migrations/`` rather than in ``scpi_driver_core``. It
inspects arbitrary Python classes and has nothing to do with SCPI, so it is not
core infrastructure; the drivers are independent packages that happen to share
this checkout.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = ["ApiSurface", "DriverUnderTest", "public_members", "surface_of"]

#: Methods that construct, tear down, or reach past the simulator. Invoking
#: these during a sweep would end the session the other checks depend on.
DEFAULT_UNSAFE_PREFIXES: tuple[str, ...] = (
    "connect",
    "close",
    "disconnect",
    "shutdown",
    "reconnect",
)


@dataclass(frozen=True)
class Member:
    """One public member of a driver class."""

    name: str
    kind: str  # "method" | "property"
    signature: str
    documented: bool = True

    def as_line(self) -> str:
        suffix = "" if self.documented else "  [undocumented]"
        return f"{self.kind} {self.name}{self.signature}{suffix}"


@dataclass
class DriverUnderTest:
    """How to inspect and exercise one driver.

    Args:
        cls: the driver class whose public surface is checked.
        make: returns a live instance backed by the driver's own simulator.
        snapshot: file recording the accepted public surface.
        annotation_gaps: file recording known-unannotated members, so existing
            gaps are tolerated while a new one fails.
        unsafe_prefixes: name prefixes never invoked during the sweep.
        skip_invoke: exact names never invoked, for cases a prefix cannot
            express.
        tolerated: exception types a swept method may legitimately raise, on
            top of the driver's own hierarchy. A simulator need not implement
            every command.
    """

    cls: type
    make: Callable[[], Any]
    snapshot: Path
    annotation_gaps: Path | None = None
    unsafe_prefixes: tuple[str, ...] = DEFAULT_UNSAFE_PREFIXES
    skip_invoke: frozenset[str] = field(default_factory=frozenset)
    tolerated: tuple[type[BaseException], ...] = ()


@dataclass(frozen=True)
class ApiSurface:
    members: tuple[Member, ...]

    def names(self) -> tuple[str, ...]:
        return tuple(m.name for m in self.members)

    def render(self) -> str:
        return "\n".join(sorted(m.as_line() for m in self.members)) + "\n"


def public_members(cls: type) -> list[Member]:
    """Every public method and property declared on ``cls`` or its bases."""
    members: list[Member] = []
    for name, value in inspect.getmembers(cls):
        if name.startswith("_"):
            continue
        if isinstance(value, property):
            members.append(
                Member(
                    name=name,
                    kind="property",
                    signature="",
                    documented=_has_doc(value.fget),
                )
            )
            continue
        if not callable(value):
            continue
        try:
            signature = str(inspect.signature(value))
        except (TypeError, ValueError):  # pragma: no cover - builtins only
            signature = "(...)"
        members.append(
            Member(
                name=name,
                kind="method",
                signature=signature,
                documented=_has_doc(value),
            )
        )
    return members


def surface_of(cls: type) -> ApiSurface:
    return ApiSurface(members=tuple(public_members(cls)))


def _has_doc(target: Any) -> bool:
    return bool((inspect.getdoc(target) or "").strip())


def undocumented(cls: type) -> list[str]:
    """Public members with no docstring, reported for the snapshot's benefit."""
    return [member.name for member in public_members(cls) if not member.documented]


def unannotated(cls: type) -> list[str]:
    """Public methods missing an annotation on a parameter or the return."""
    missing = []
    for member in public_members(cls):
        if member.kind != "method":
            continue
        function = getattr(cls, member.name)
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):  # pragma: no cover
            continue
        if signature.return_annotation is inspect.Signature.empty:
            missing.append(f"{member.name} (return)")
        for index, parameter in enumerate(signature.parameters.values()):
            if index == 0 and parameter.name in ("self", "cls"):
                continue
            if parameter.annotation is inspect.Signature.empty:
                missing.append(f"{member.name}({parameter.name})")
    return missing


def invocable_without_arguments(driver: DriverUnderTest) -> list[str]:
    """Public methods the sweep may safely call on a simulated instance."""
    names = []
    for member in public_members(driver.cls):
        if member.kind != "method":
            continue
        if member.name in driver.skip_invoke:
            continue
        if member.name.startswith(driver.unsafe_prefixes):
            continue
        attribute = inspect.getattr_static(driver.cls, member.name, None)
        if isinstance(attribute, (classmethod, staticmethod)):
            # Constructors and helpers; they do not act on a live session.
            continue
        try:
            signature = inspect.signature(getattr(driver.cls, member.name))
        except (TypeError, ValueError):  # pragma: no cover
            continue
        required = [
            parameter
            for parameter in list(signature.parameters.values())[1:]
            if parameter.default is inspect.Parameter.empty
            and parameter.kind
            not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        ]
        if not required:
            names.append(member.name)
    return names


def check_annotation_gaps(driver: DriverUnderTest) -> list[str]:
    """Return annotation gaps that are not in the recorded set.

    Anything here is new, and therefore this change's responsibility.
    """
    current = set(unannotated(driver.cls))
    if driver.annotation_gaps is None or not driver.annotation_gaps.exists():
        return sorted(current)
    recorded = {
        line.strip()
        for line in driver.annotation_gaps.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    return sorted(current - recorded)


def write_annotation_gaps(driver: DriverUnderTest) -> None:
    """Record the current annotation gaps. Run deliberately, never from a test."""
    if driver.annotation_gaps is None:
        return
    driver.annotation_gaps.parent.mkdir(parents=True, exist_ok=True)
    gaps = sorted(unannotated(driver.cls))
    driver.annotation_gaps.write_text(
        ("\n".join(gaps) + "\n") if gaps else "", encoding="utf-8"
    )


def check_snapshot(driver: DriverUnderTest) -> tuple[list[str], list[str]]:
    """Return ``(removed, added)`` relative to the recorded surface.

    Removals are breaking changes for callers. Additions are not, but are
    surfaced so the snapshot is updated deliberately rather than drifting.
    """
    current = surface_of(driver.cls).render().splitlines()
    if not driver.snapshot.exists():
        raise AssertionError(
            f"no API snapshot at {driver.snapshot}; "
            "generate it with scripts/update_api_snapshot.py"
        )
    recorded = driver.snapshot.read_text(encoding="utf-8").splitlines()
    removed = [line for line in recorded if line not in current]
    added = [line for line in current if line not in recorded]
    return removed, added


def write_snapshot(driver: DriverUnderTest) -> None:
    """Record the current surface. Run deliberately, never from a test."""
    driver.snapshot.parent.mkdir(parents=True, exist_ok=True)
    driver.snapshot.write_text(surface_of(driver.cls).render(), encoding="utf-8")


def sweep(driver: DriverUnderTest) -> dict[str, str]:
    """Invoke every no-argument method on a fresh simulated instance.

    Each call gets its own instance, so one method leaving the driver in an odd
    state cannot make the next one fail for the wrong reason.

    Returns:
        A mapping of method name to the unexpected exception it raised, empty
        when every method behaved.
    """
    base = driver.cls.__module__.split(".")[0]
    failures: dict[str, str] = {}
    for name in invocable_without_arguments(driver):
        instance = driver.make()
        try:
            getattr(instance, name)()
        except driver.tolerated:
            continue
        except BaseException as exc:  # noqa: BLE001 - the point is to classify it
            if _belongs_to(exc, base):
                # The driver rejected it in its own vocabulary, which is a
                # legitimate answer from a simulator that lacks the command.
                continue
            failures[name] = f"{type(exc).__name__}: {exc}"
        finally:
            _close_quietly(instance)
    return failures


def read_properties(driver: DriverUnderTest) -> dict[str, str]:
    """Read every public property once, reporting any that raise unexpectedly."""
    base = driver.cls.__module__.split(".")[0]
    instance = driver.make()
    failures: dict[str, str] = {}
    try:
        for member in public_members(driver.cls):
            if member.kind != "property":
                continue
            try:
                getattr(instance, member.name)
            except driver.tolerated:
                continue
            except BaseException as exc:  # noqa: BLE001 - classified below
                if _belongs_to(exc, base):
                    continue
                failures[member.name] = f"{type(exc).__name__}: {exc}"
    finally:
        _close_quietly(instance)
    return failures


def _belongs_to(exc: BaseException, package: str) -> bool:
    """Whether ``exc`` comes from the driver's own exception hierarchy."""
    return type(exc).__module__.split(".")[0] == package


def _close_quietly(instance: Any) -> None:
    for name in ("close", "disconnect"):
        closer = getattr(instance, name, None)
        if callable(closer):
            try:
                closer()
            except BaseException:  # noqa: BLE001 - teardown must not mask a result
                pass
            return
