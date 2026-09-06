# Guide: diagnosing a failed E-Resistor test run

A short, task-oriented companion to `docs/logging_and_evidence.md` (which
describes the evidence system itself).

## "A test failed in CI/on a bench I can't access — what happened?"

1. Ask whoever ran it for the evidence run directory, or for the zip from
   `Export Diagnostic Bundle` if they called it (or add the keyword call to
   the failing suite's teardown so it's captured automatically next time —
   see below).
2. Open `run_summary.md` first — it's the one-paragraph version.
3. Open `events/errors.jsonl`. Each line is one exception; find the one whose
   `capability` matches the keyword Robot reported as failing.
4. Note its `operation_id`. Search `events/operations.jsonl` for that ID to
   see the exact arguments Robot passed in.
5. Search `protocol/exchanges.jsonl` for the same `operation_id` to see
   exactly which SCPI commands or HTTP requests that keyword made before
   failing — this tells you whether the failure was in argument validation
   (no exchanges logged) or partway through a calibration download or a
   multi-channel resistance write (some but not all channels logged).

## "I want every future failure on this bench to leave a diagnostic bundle automatically"

Add `Export Diagnostic Bundle` to suite teardown, guarded so it always runs
even after a failure:

```robotframework
*** Settings ***
Library         rf_eresistor.EResistorLibrary    host=192.168.0.55
Suite Setup     Connect To EResistor    all_off_on_connect=${True}
Suite Teardown  Teardown With Diagnostics

*** Keywords ***
Teardown With Diagnostics
    Run Keyword And Ignore Error    Open All EResistor Channels
    ${bundle}=    Export Diagnostic Bundle
    Log    Diagnostic bundle: ${bundle}    console=True
    Disconnect From EResistor
```

## "Did this run actually touch real hardware?"

Check `execution_mode` in `run_summary.json`: currently always
`REAL_HARDWARE`, since this driver has no bundled simulator and unit tests
bypass `connect()` entirely with a hand-rolled `FakeClient`. See
`docs/logging_and_evidence.md`'s "Simulation honesty" section.

## "I just want to turn this off"

```robotframework
Library    rf_eresistor.EResistorLibrary    host=192.168.0.55    evidence_enabled=${FALSE}
```

Nothing gets written to `results/`. Exceptions still reach Robot's own log,
the standard Python logger, and `AuditLogger` (if `audit_log_file` is set) —
you lose the structured, correlated record, not the error itself.

## Validating that a run directory wasn't tampered with or truncated

```console
python scripts/validate_evidence.py results/session/rf_eresistor/<run>/
```

Reports any hash mismatch, missing file, or JSONL stream with a gap or
duplicate in its `sequence` numbers. Exit code is non-zero on any finding.
