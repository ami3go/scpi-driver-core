# Guide: diagnosing a failed oscilloscope test run

A short, task-oriented companion to `docs/logging_and_evidence.md` (which
describes the evidence system itself).

## "A test failed on a bench I can't access — what happened?"

1. Get the evidence run directory, or the zip from `Export Diagnostic
   Bundle` if it was called (add it to suite teardown — see below — so it's
   captured automatically next time).
2. Open `run_summary.md` first — it's the one-paragraph version.
3. Open `events/errors.jsonl`. Each line is one exception; find the one whose
   `capability` matches the keyword Robot reported as failing.
4. Note its `operation_id`. Search `events/operations.jsonl` for that ID to
   see the exact arguments Robot passed in.
5. Search `protocol/exchanges.jsonl` for the same `operation_id` to see
   exactly which SCPI commands/queries that keyword sent, and what the
   instrument replied, before failing.

## "I want every future failure on this bench to leave a diagnostic bundle automatically"

```robotframework
*** Settings ***
Library         rf_tbs1000c.Tbs1000cLibrary
Suite Setup     Connect    resource=${RESOURCE}
Suite Teardown  Teardown With Diagnostics

*** Keywords ***
Teardown With Diagnostics
    ${bundle}=    Export Diagnostic Bundle
    Log    Diagnostic bundle: ${bundle}    console=True
    Disconnect
```

Robot's own suite-end listener hook (`_end_suite`) finalizes
`run_summary.json`/`evidence_manifest.json` right after teardown runs, so the
bundle captured above already has a consistent manifest even before that
final finalize step — `Export Diagnostic Bundle` refreshes the manifest
itself when called.

## "Did this run actually touch real hardware?"

Check `execution_mode` in `run_summary.json`/`run_summary.md`:
`REAL_HARDWARE`, `SIMULATOR`, or `MIXED` if the run connected to both a real
instrument and the bundled simulator (uncommon, but possible with two
different aliases in one suite). See RFDS-008 §6.6 ("simulation honesty") for
why this is recorded explicitly.

## "I just want to turn this off"

```robotframework
Library    rf_tbs1000c.Tbs1000cLibrary    evidence_enabled=${FALSE}
```

Nothing gets written to `results/`. Exceptions still reach Robot's own log
and the standard Python logger.

## "Was a waveform transfer actually attempted, and how big was it?"

`Get Waveform`, `Save Waveform To CSV`, and the on-instrument save/recall
keywords all go through `query_binary`/`write_binary`, which the protocol
trace records as `<N bytes, sha256=...>` rather than dumping the raw IEEE
block into JSON — search `protocol/exchanges.jsonl` for the relevant
`operation_id` to confirm a transfer happened and how large it was, without
needing the actual sample data (which stays only in the returned Robot
value/host file, per RFDS-008 §24.1's binary-trace guidance).

## Validating that a run directory wasn't tampered with or truncated

```console
python scripts/validate_evidence.py results/session/rf_tbs1000c/<run>/
```

Reports any hash mismatch, missing file, or JSONL stream with a gap or
duplicate in its `sequence` numbers. Exit code is non-zero on any finding.
