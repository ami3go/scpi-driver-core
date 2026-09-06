"""Tests for the gates. These touch no hardware and are safe to run anywhere.

Two things are being pinned. The obvious one is that each gate blocks. The less
obvious and more important one is that the gates can *pass* — a gate that is
unconditionally closed protects nothing and hides the fact that it was never
really wired up. So there is a test that assembles a fully configured, signed
setup and asserts the gate list comes back empty.

The shipped allowlists are also checked: every one must be unsigned, so a fresh
clone of this repository cannot sweep anything.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import generate_allowlist  # noqa: E402
from sweep import (  # noqa: E402
    CONFIRMATION_PHRASE,
    Allowlist,
    AllowlistError,
    SignOff,
    gate_failures,
    load_allowlist,
    resource_variable,
    run_sweep,
)

ALLOWLISTS = Path(__file__).resolve().parent / "allowlists"

SIGNED = """
driver = "py_demo"
read_only = ["identify", "get_frequency"]

[sign_off]
signed_off_by = "A. Person"
signed_off_date = "2026-09-06"
instrument_serial = "MY12345678"
allow_writes = false
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "py_demo.toml"
    path.write_text(text, encoding="utf-8")
    return path


def full_environment() -> dict[str, str]:
    return {
        "SCPI_HARDWARE_SWEEP": "1",
        "SCPI_HARDWARE_CONFIRM": CONFIRMATION_PHRASE,
        resource_variable("py_demo"): "TCPIP0::192.168.0.10::inst0::INSTR",
    }


# -- the gates open ---------------------------------------------------------


def test_a_fully_configured_signed_setup_passes_every_gate(tmp_path: Path) -> None:
    """Without this, the rest of the file proves only that nothing works."""
    reasons = gate_failures(
        driver="py_demo",
        allowlist_path=write(tmp_path, SIGNED),
        environ=full_environment(),
        proposed_read_only=["identify", "get_frequency"],
    )
    assert reasons == []


# -- the gates close --------------------------------------------------------


def test_nothing_runs_with_an_empty_environment(tmp_path: Path) -> None:
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, SIGNED), environ={}
    )
    assert any("SCPI_HARDWARE_SWEEP" in r for r in reasons)
    assert any("SCPI_HARDWARE_CONFIRM" in r for r in reasons)
    assert any(resource_variable("py_demo") in r for r in reasons)


@pytest.mark.parametrize(
    "variable",
    ["SCPI_HARDWARE_SWEEP", "SCPI_HARDWARE_CONFIRM", resource_variable("py_demo")],
)
def test_removing_any_single_gate_blocks_the_sweep(tmp_path: Path, variable: str) -> None:
    """Each gate is independently sufficient to stop the run."""
    environment = full_environment()
    del environment[variable]
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, SIGNED), environ=environment
    )
    assert reasons, f"removing {variable} did not block the sweep"


def test_an_approximate_confirmation_phrase_is_not_accepted(tmp_path: Path) -> None:
    """It is a deliberate-action token; close enough is not the point."""
    environment = full_environment()
    environment["SCPI_HARDWARE_CONFIRM"] = CONFIRMATION_PHRASE.upper()
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, SIGNED), environ=environment
    )
    assert any("SCPI_HARDWARE_CONFIRM" in r for r in reasons)


def test_a_blank_resource_string_is_not_a_resource_string(tmp_path: Path) -> None:
    environment = full_environment()
    environment[resource_variable("py_demo")] = "   "
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, SIGNED), environ=environment
    )
    assert any("no default address" in r for r in reasons)


# -- the allowlist ----------------------------------------------------------


def test_a_missing_allowlist_blocks(tmp_path: Path) -> None:
    reasons = gate_failures(
        driver="py_demo",
        allowlist_path=tmp_path / "absent.toml",
        environ=full_environment(),
    )
    assert any("no allowlist" in r for r in reasons)


def test_malformed_toml_is_unsafe_not_empty(tmp_path: Path) -> None:
    """A parse failure must never read as 'nothing to worry about'."""
    with pytest.raises(AllowlistError, match="not valid TOML"):
        load_allowlist(write(tmp_path, "driver = [unclosed"))


@pytest.mark.parametrize("field", ["signed_off_by", "signed_off_date", "instrument_serial"])
def test_a_partially_signed_allowlist_blocks(tmp_path: Path, field: str) -> None:
    """All three are required: a name with no unit does not say what was checked."""
    text = SIGNED.replace(f'{field} = "', f'{field} = ""  # was: "')
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, text), environ=full_environment()
    )
    assert any("unsigned" in r for r in reasons)


def test_an_allowlist_for_another_driver_blocks(tmp_path: Path) -> None:
    """Sweeping the right list against the wrong instrument is the accident."""
    text = SIGNED.replace('driver = "py_demo"', 'driver = "py_other"')
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, text), environ=full_environment()
    )
    assert any("is for 'py_other'" in r for r in reasons)


def test_an_empty_allowlist_blocks(tmp_path: Path) -> None:
    text = SIGNED.replace('read_only = ["identify", "get_frequency"]', "read_only = []")
    reasons = gate_failures(
        driver="py_demo", allowlist_path=write(tmp_path, text), environ=full_environment()
    )
    assert any("lists no methods" in r for r in reasons)


def test_a_hand_added_method_is_rejected(tmp_path: Path) -> None:
    """The list cannot quietly drift away from what static analysis proposed."""
    reasons = gate_failures(
        driver="py_demo",
        allowlist_path=write(tmp_path, SIGNED),
        environ=full_environment(),
        proposed_read_only=["identify"],  # get_frequency was added by hand
    )
    assert any("get_frequency" in r for r in reasons)


def test_a_hand_added_method_is_allowed_when_writes_are_accepted(tmp_path: Path) -> None:
    """Deliberate is fine; silent is not."""
    text = SIGNED.replace("allow_writes = false", "allow_writes = true")
    reasons = gate_failures(
        driver="py_demo",
        allowlist_path=write(tmp_path, text),
        environ=full_environment(),
        proposed_read_only=["identify"],
    )
    assert reasons == []


# -- what ships in this repository ------------------------------------------


def test_every_shipped_allowlist_is_unsigned() -> None:
    """A fresh clone must not be able to sweep anything."""
    files = sorted(ALLOWLISTS.glob("py_*.toml"))
    assert len(files) == 8
    for path in files:
        assert not load_allowlist(path).sign_off.is_signed, f"{path} ships signed"


def test_every_shipped_allowlist_is_blocked_right_now() -> None:
    for path in sorted(ALLOWLISTS.glob("py_*.toml")):
        assert gate_failures(driver=path.stem, allowlist_path=path, environ={})


def test_no_shipped_allowlist_enables_writes() -> None:
    for path in sorted(ALLOWLISTS.glob("py_*.toml")):
        assert not load_allowlist(path).sign_off.allow_writes, f"{path} allows writes"


def test_shipped_allowlists_contain_only_statically_proposed_methods() -> None:
    """The files on disk must match what the generator would produce today."""
    for path in sorted(ALLOWLISTS.glob("py_*.toml")):
        listed = set(load_allowlist(path).read_only)
        assert listed, f"{path} is empty"
        assert not any(generate_allowlist.DANGEROUS.search(name) for name in listed), path


# -- the runner -------------------------------------------------------------


class FakeDriver:
    """Records what was called, and can lose its connection on cue."""

    def __init__(self, *, lose_link_after: str | None = None) -> None:
        self.calls: list[str] = []
        self.connected = True
        self._lose_after = lose_link_after

    def _record(self, name: str) -> str:
        self.calls.append(name)
        if name == self._lose_after:
            self.connected = False
        return f"{name}-value"

    def identify(self) -> str:
        return self._record("identify")

    def get_frequency(self) -> str:
        return self._record("get_frequency")

    def get_amplitude(self) -> str:
        return self._record("get_amplitude")

    def raises(self) -> str:
        raise ValueError("instrument said no")


def allowlist(*names: str) -> Allowlist:
    return Allowlist(
        driver="py_demo",
        sign_off=SignOff("A. Person", "2026-09-06", "MY12345678"),
        read_only=names,
    )


def test_the_sweep_calls_every_allowlisted_method() -> None:
    driver = FakeDriver()
    report = run_sweep(
        driver="py_demo",
        instance=driver,
        allowlist=allowlist("get_frequency", "get_amplitude"),
        identity=lambda: "AGILENT,33220A,MY123,1.0",
        expected_identity="33220A",
        still_connected=lambda: driver.connected,
    )
    assert driver.calls == ["get_frequency", "get_amplitude"]
    assert not report.failures


def test_the_wrong_instrument_aborts_before_anything_is_called() -> None:
    """The allowlist is only meaningful for the unit it was signed for."""
    driver = FakeDriver()
    with pytest.raises(RuntimeError, match="refusing to sweep"):
        run_sweep(
            driver="py_demo",
            instance=driver,
            allowlist=allowlist("get_frequency"),
            identity=lambda: "KEYSIGHT,N6700C,MY999,1.0",
            expected_identity="33220A",
            still_connected=lambda: driver.connected,
        )
    assert driver.calls == []


def test_the_sweep_stops_when_the_link_is_lost() -> None:
    """Continuing would pile failures on a dead link and hide the cause."""
    driver = FakeDriver(lose_link_after="get_frequency")
    report = run_sweep(
        driver="py_demo",
        instance=driver,
        allowlist=allowlist("get_frequency", "get_amplitude"),
        identity=lambda: "33220A",
        expected_identity="33220A",
        still_connected=lambda: driver.connected,
    )
    assert driver.calls == ["get_frequency"]
    assert report.aborted_after == "get_frequency"


def test_a_method_the_driver_does_not_have_is_skipped_not_guessed() -> None:
    driver = FakeDriver()
    report = run_sweep(
        driver="py_demo",
        instance=driver,
        allowlist=allowlist("get_frequency", "get_nonexistent"),
        identity=lambda: "33220A",
        expected_identity="33220A",
        still_connected=lambda: driver.connected,
    )
    assert report.skipped == ["get_nonexistent"]
    assert driver.calls == ["get_frequency"]


def test_a_failure_is_recorded_and_the_sweep_continues() -> None:
    driver = FakeDriver()
    report = run_sweep(
        driver="py_demo",
        instance=driver,
        allowlist=allowlist("raises", "get_frequency"),
        identity=lambda: "33220A",
        expected_identity="33220A",
        still_connected=lambda: driver.connected,
    )
    assert [f.name for f in report.failures] == ["raises"]
    assert "ValueError: instrument said no" in report.failures[0].error
    assert driver.calls == ["get_frequency"]


def test_a_tolerated_exception_counts_as_an_answer() -> None:
    driver = FakeDriver()
    report = run_sweep(
        driver="py_demo",
        instance=driver,
        allowlist=allowlist("raises"),
        identity=lambda: "33220A",
        expected_identity="33220A",
        still_connected=lambda: driver.connected,
        tolerated=(ValueError,),
    )
    assert not report.failures


def test_the_transcript_records_every_call_as_jsonl(tmp_path: Path) -> None:
    """Groundwork: real traffic is what a replay harness would be built from."""
    driver = FakeDriver()
    path = tmp_path / "nested" / "transcript.jsonl"
    run_sweep(
        driver="py_demo",
        instance=driver,
        allowlist=allowlist("get_frequency", "get_nonexistent"),
        identity=lambda: "33220A",
        expected_identity="33220A",
        still_connected=lambda: driver.connected,
        transcript=path,
    )
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [r["event"] for r in records] == ["identified", "call", "skipped"]
    assert records[1]["method"] == "get_frequency"
    assert records[1]["ok"] is True
