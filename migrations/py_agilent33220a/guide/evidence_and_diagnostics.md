# Guide: diagnosing a failed waveform-generator test run

A short, task-oriented companion to `docs/logging_and_evidence.md`.

## "A test failed on a bench I can't access — what happened?"

1. Get the evidence run directory (or the zip from `Export Diagnostic
   Bundle`, if the suite calls it — see below).
2. Open `run_summary.md` first — the one-paragraph version, including
   whether this was a real-hardware, simulated, or mixed run.
3. Open `events/errors.jsonl`. Each line is one exception; find the one
   whose `capability` matches the keyword Robot reported as failing.
4. Note its `operation_id`. Search `events/operations.jsonl` for that ID to
   see the exact arguments Robot passed.
5. Search `protocol/exchanges.jsonl` (or just read `protocol/
   outbound_trace.log`/`inbound_trace.log` directly — they're plain SCPI
   text) for the same `operation_id` to see exactly which SCPI commands that
   keyword sent, and what the instrument replied, before it failed.

## "I want every future failure on this bench to leave a diagnostic bundle automatically"

```robotframework
*** Settings ***
Library         rf_agilent33220a.Agilent33220ALibrary
Suite Setup     Connect    resource=USB0::0x0957::0x0407::<serial>::INSTR
Suite Teardown  Teardown With Diagnostics

*** Keywords ***
Teardown With Diagnostics
    ${bundle}=    Export Diagnostic Bundle
    Log    Diagnostic bundle: ${bundle}    console=True
    Disconnect
```

## "Did this run actually touch real hardware?"

Check `execution_mode` in `run_summary.json`/`run_summary.md`:
`REAL_HARDWARE`, `SIMULATOR`, `MIXED`, or `NO_HARDWARE`. A suite that only
ever called `Connect simulated=${TRUE}` will show `SIMULATOR` — see RFDS-008
§6.6 ("simulation honesty").

## "I just want to turn this off"

```robotframework
Library    rf_agilent33220a.Agilent33220ALibrary    evidence_enabled=${FALSE}
```

Exceptions still reach Robot's own log and the standard Python logger — only
the structured run directory is skipped.

## Validating that a run directory wasn't tampered with or truncated

```console
python scripts/validate_evidence.py results/session/rf_agilent33220a/<run>/
```

Reports any hash mismatch, missing file, or JSONL stream with a gap or
duplicate in its `sequence` numbers. Exit code is non-zero on any finding.
