# Guide: diagnosing a failed EA-PS 9000 T test run

A short, task-oriented companion to `docs/logging_and_evidence.md` (which
describes the evidence system itself).

## "A test failed — what happened?"

1. Ask whoever ran it for the evidence run directory (`results/session/
   rf_ea_ps9000t/<run>/`), or for the zip from `Export Diagnostic Bundle` if
   they called it.
2. Open `run_summary.md` first — it's the one-paragraph version.
3. Open `events/errors.jsonl`. Each line is one exception; find the one whose
   `capability` matches the keyword Robot reported as failing, and note its
   `session_alias` if more than one power supply was connected.
4. Note its `operation_id`. Search `events/operations.jsonl` for that ID to
   see the exact arguments Robot passed in.
5. Search `protocol/exchanges.jsonl` for the same `operation_id` to see the
   exact SCPI commands sent and raw responses received before the failure —
   this tells you whether the failure was in argument validation (no SCPI
   traffic logged) or a device-side rejection (a command was sent, and either
   no response came back before timeout, or the response itself was the
   problem).

## "I want every future failure on this bench to leave a diagnostic bundle automatically"

```robotframework
*** Settings ***
Library         rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup     Connect    com_port=5    alias=bench
Suite Teardown  Teardown With Diagnostics

*** Keywords ***
Teardown With Diagnostics
    ${bundle}=    Export Diagnostic Bundle    alias=bench
    Log    Diagnostic bundle: ${bundle}    console=True
    Disconnect    bench
```

## "Did this run actually touch real hardware?"

Check `execution_mode` in `run_summary.json` (also shown in
`run_summary.md`): `REAL_HARDWARE` for a VISA connection, `SIMULATOR` for
`Connect simulated=${TRUE}`. This driver's simulator (`ea_ps9000t/simulator.py`)
parses real SCPI text, so `protocol/exchanges.jsonl` looks the same shape
either way — `execution_mode` is what tells you which one actually ran.

## "I have multiple power supplies connected — whose evidence am I looking at?"

Each alias gets its own run directory (a new `<timestamp>_<run_id>` folder
per `Connect` call), so just match `session_alias` in the JSONL records, or
the `device_identity.json`'s `resource` field, against the bench you're
investigating.

## "I just want to turn this off"

```robotframework
Library    rf_ea_ps9000t.EaPs9000TLibrary    evidence_enabled=${FALSE}
```

Nothing gets written to `results/`. Exceptions still reach Robot's own log
and the standard Python logger — you lose the structured record and the SCPI
trace, not the error itself.

## Validating that a run directory wasn't tampered with or truncated

```console
python scripts/validate_evidence.py results/session/rf_ea_ps9000t/<run>/
```

Reports any hash mismatch, missing file, or JSONL stream with a gap or
duplicate in its `sequence` numbers. Exit code is non-zero on any finding.
