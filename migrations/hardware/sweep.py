"""The gated hardware sweep: call a driver's read-only API on a real instrument.

Written to be read before it is run. Nothing here has ever touched hardware.

The conformance sweep in ``migrations/driver_api_conformance.py`` calls every
no-argument method of a driver, and its docstring says in capital letters that
it must never be pointed at an instrument, because blindly invoking every
method would enable outputs. This module is the version that may be, and the
whole design is about the distance between those two sentences.

Five gates, each of which fails closed. All five must pass before a single byte
is transmitted:

1. ``SCPI_HARDWARE_SWEEP=1``. Nothing runs by accident or by default.
2. ``SCPI_HARDWARE_CONFIRM`` equals :data:`CONFIRMATION_PHRASE`. Not a secret
   and not a password — it is a deliberate-action token, the same idea as
   :class:`~scpi_driver_core.execution.guards.ConfirmationGuard`. Typing it
   takes a moment's thought, which is the point.
3. A resource string in ``SCPI_HARDWARE_<DRIVER>_RESOURCE``. There is no
   default address, so a sweep cannot wander onto whatever happens to answer.
4. A signed allowlist: ``signed_off_by``, ``signed_off_date`` and
   ``instrument_serial`` all filled in. Signing is a person saying they know
   what is wired to this unit.
5. Every listed method still passes static analysis — public, no arguments,
   sends only queries, not name-matched as dangerous. A method hand-added to
   the list is rejected unless ``allow_writes`` is also set, which is a second
   deliberate act. The list cannot drift away from what was signed for.

Then at run time, before anything else, the instrument's ``*IDN?`` must match
what the caller expected. Sweeping the right method list against the wrong
instrument is exactly the accident the allowlist exists to prevent.

Every call is recorded to a JSONL transcript. That is deliberate groundwork: a
transcript of real traffic is what a future replay harness would need to turn
one bench session into a regression suite that runs forever afterwards.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - 3.10 needs the backport
    import tomli as tomllib  # type: ignore[no-redef]

#: Typed into ``SCPI_HARDWARE_CONFIRM`` by a person who has looked at the bench.
#: A phrase rather than a flag, so it cannot be set by muscle memory, and not a
#: credential: it is echoed in error messages on purpose.
CONFIRMATION_PHRASE = "yes I have checked what is connected"

__all__ = [
    "CONFIRMATION_PHRASE",
    "AllowlistError",
    "MethodResult",
    "SignOff",
    "Allowlist",
    "SweepReport",
    "gate_failures",
    "load_allowlist",
    "resource_variable",
    "run_sweep",
]


class AllowlistError(Exception):
    """The allowlist file is missing, malformed, or unsigned."""


@dataclass(frozen=True)
class SignOff:
    """Who accepted these calls being made, and to which physical unit."""

    signed_off_by: str
    signed_off_date: str
    instrument_serial: str
    allow_writes: bool = False

    @property
    def is_signed(self) -> bool:
        return bool(
            self.signed_off_by.strip()
            and self.signed_off_date.strip()
            and self.instrument_serial.strip()
        )


@dataclass(frozen=True)
class Allowlist:
    """The methods a person has accepted being called on real hardware."""

    driver: str
    sign_off: SignOff
    read_only: tuple[str, ...]


@dataclass
class MethodResult:
    """What one call did."""

    name: str
    ok: bool
    elapsed_s: float
    value: str | None = None
    error: str | None = None


@dataclass
class SweepReport:
    """The outcome of a sweep."""

    driver: str
    identity: str
    results: list[MethodResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    aborted_after: str | None = None

    @property
    def failures(self) -> list[MethodResult]:
        return [r for r in self.results if not r.ok]


def resource_variable(driver: str) -> str:
    """The environment variable holding this driver's resource string."""
    return f"SCPI_HARDWARE_{driver.upper()}_RESOURCE"


def load_allowlist(path: Path) -> Allowlist:
    """Parse an allowlist file.

    Raises:
        AllowlistError: if it is missing or does not have the expected shape.
            Malformed is treated as unsafe, never as empty.
    """
    if not path.is_file():
        raise AllowlistError(f"no allowlist at {path}")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise AllowlistError(f"{path} is not valid TOML: {exc}") from exc

    try:
        sign_off_table = data["sign_off"]
        allowlist = Allowlist(
            driver=str(data["driver"]),
            sign_off=SignOff(
                signed_off_by=str(sign_off_table.get("signed_off_by", "")),
                signed_off_date=str(sign_off_table.get("signed_off_date", "")),
                instrument_serial=str(sign_off_table.get("instrument_serial", "")),
                allow_writes=bool(sign_off_table.get("allow_writes", False)),
            ),
            read_only=tuple(str(name) for name in data.get("read_only", [])),
        )
    except (KeyError, TypeError, AttributeError) as exc:
        raise AllowlistError(f"{path} is missing required fields: {exc}") from exc
    return allowlist


def gate_failures(
    *,
    driver: str,
    allowlist_path: Path,
    environ: Mapping[str, str] | None = None,
    proposed_read_only: Iterable[str] | None = None,
) -> list[str]:
    """Every reason this sweep must not run. Empty means all gates passed.

    Every reason is collected rather than the first one returned, so a person
    setting this up sees the whole list instead of discovering it one run at a
    time.

    Args:
        driver: the project name, e.g. ``py_keysight_n6700``.
        allowlist_path: the signed allowlist for that driver.
        environ: the environment to read; defaults to the real one.
        proposed_read_only: what static analysis currently proposes. When given,
            the allowlist may not exceed it unless ``allow_writes`` is set.

    Returns:
        Human-readable reasons, one per unmet gate.
    """
    environ = os.environ if environ is None else environ
    reasons: list[str] = []

    if environ.get("SCPI_HARDWARE_SWEEP") != "1":
        reasons.append("SCPI_HARDWARE_SWEEP is not set to 1")

    confirmation = environ.get("SCPI_HARDWARE_CONFIRM", "")
    if confirmation != CONFIRMATION_PHRASE:
        reasons.append(
            f"SCPI_HARDWARE_CONFIRM must be exactly {CONFIRMATION_PHRASE!r}, "
            f"got {confirmation!r}"
        )

    variable = resource_variable(driver)
    if not environ.get(variable, "").strip():
        reasons.append(f"{variable} is not set; there is no default address")

    try:
        allowlist = load_allowlist(allowlist_path)
    except AllowlistError as exc:
        reasons.append(str(exc))
        return reasons

    if allowlist.driver != driver:
        reasons.append(f"{allowlist_path} is for {allowlist.driver!r}, not {driver!r}")
    if not allowlist.sign_off.is_signed:
        reasons.append(
            f"{allowlist_path} is unsigned: signed_off_by, signed_off_date and "
            f"instrument_serial must all be filled in"
        )
    if not allowlist.read_only:
        reasons.append(f"{allowlist_path} lists no methods to call")

    if proposed_read_only is not None and not allowlist.sign_off.allow_writes:
        proposed = set(proposed_read_only)
        added = sorted(set(allowlist.read_only) - proposed)
        if added:
            reasons.append(
                "the allowlist contains methods static analysis does not consider "
                f"read-only: {', '.join(added)}. Either they now write, or they were "
                "added by hand. Set allow_writes to accept them deliberately."
            )
    return reasons


def run_sweep(
    *,
    driver: str,
    instance: Any,
    allowlist: Allowlist,
    identity: Callable[[], str],
    expected_identity: str,
    still_connected: Callable[[], bool],
    transcript: Path | None = None,
    tolerated: Sequence[type[BaseException]] = (),
    clock: Callable[[], float] = time.monotonic,
) -> SweepReport:
    """Call every allowlisted method once, in order, recording what happened.

    The gates are the caller's job; by the time this runs, the decision to
    talk to hardware has already been made and audited. What this adds is
    care during the run:

    * the instrument is identified first, and a mismatch aborts before any
      other call;
    * a method missing from the driver is skipped rather than guessed at;
    * the connection is checked after every call, and the sweep stops the
      moment it is lost — continuing would just pile failures onto a dead
      link and obscure which call caused it.

    Args:
        driver: project name, recorded in the transcript.
        instance: the connected driver.
        allowlist: the signed list; only ``read_only`` is called.
        identity: returns the instrument's identity string.
        expected_identity: substring that must appear in it.
        still_connected: whether the link survived the last call.
        transcript: where to append the JSONL record, if anywhere.
        tolerated: exception types counted as an answer rather than a failure,
            for drivers that raise their own type for an unsupported query.
        clock: monotonic time source, injectable for tests.

    Returns:
        What every call did, and where the sweep stopped if it did.

    Raises:
        RuntimeError: if the instrument is not the one expected.
    """
    found = identity()
    if expected_identity not in found:
        raise RuntimeError(
            f"refusing to sweep: expected an instrument identifying as "
            f"{expected_identity!r}, but *IDN? returned {found!r}"
        )

    report = SweepReport(driver=driver, identity=found)
    records: list[dict[str, object]] = [
        {"event": "identified", "driver": driver, "identity": found}
    ]

    for name in allowlist.read_only:
        method = getattr(instance, name, None)
        if not callable(method):
            report.skipped.append(name)
            records.append({"event": "skipped", "method": name, "reason": "not callable"})
            continue

        started = clock()
        try:
            value = method()
        except (KeyboardInterrupt, SystemExit):
            raise  # an operator stopping the sweep is not a test result
        except BaseException as exc:  # noqa: BLE001 - every outcome is recorded
            result = MethodResult(
                name=name,
                ok=bool(tolerated) and isinstance(exc, tuple(tolerated)),
                elapsed_s=clock() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        else:
            result = MethodResult(
                name=name, ok=True, elapsed_s=clock() - started, value=repr(value)[:200]
            )
        report.results.append(result)
        records.append(
            {
                "event": "call",
                "method": name,
                "ok": result.ok,
                "elapsed_s": round(result.elapsed_s, 6),
                "value": result.value,
                "error": result.error,
            }
        )

        if not still_connected():
            report.aborted_after = name
            records.append({"event": "aborted", "after": name, "reason": "link lost"})
            break

    if transcript is not None:
        transcript.parent.mkdir(parents=True, exist_ok=True)
        with transcript.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record) + "\n")
    return report


def _main() -> int:
    """Print, for every driver, what a sweep would call and why it cannot run.

    A dry run: it reads files and the environment, connects to nothing, and is
    the intended way to inspect the plan before a bench session.
    """
    import argparse

    parser = argparse.ArgumentParser(description=_main.__doc__)
    parser.add_argument(
        "--allowlists", type=Path, default=Path(__file__).resolve().parent / "allowlists"
    )
    arguments = parser.parse_args()

    runnable = 0
    for path in sorted(arguments.allowlists.glob("py_*.toml")):
        driver = path.stem
        print(f"== {driver}")
        try:
            allowlist = load_allowlist(path)
        except AllowlistError as exc:
            print(f"   unusable allowlist: {exc}\n")
            continue
        print(f"   would call {len(allowlist.read_only)} methods: "
              f"{', '.join(allowlist.read_only[:6])}"
              f"{', …' if len(allowlist.read_only) > 6 else ''}")
        reasons = gate_failures(driver=driver, allowlist_path=path)
        if reasons:
            print("   blocked by:")
            for reason in reasons:
                print(f"     - {reason}")
        else:
            runnable += 1
            print("   all gates pass; a sweep would connect and run")
        print()
    print(f"{runnable} of 8 drivers would run right now")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
