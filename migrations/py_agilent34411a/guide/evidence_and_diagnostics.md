# Guide: diagnosing a failed measurement test run

A short, task-oriented companion to `docs/logging_and_evidence.md`.

## "A test failed — what happened?"

1. Open `run_summary.md` first — the one-paragraph version.
2. Open `events/errors.jsonl`. Each line is one exception; find the one whose
   `capability` matches the keyword Robot reported as failing, and note its
   `session_alias` if this suite used more than one connection.
3. Note its `operation_id`. Search `events/operations.jsonl` for that ID to
   see the exact arguments Robot passed in.
4. Search `protocol/exchanges.jsonl` for the same `operation_id` to see
   exactly which SCPI commands were sent and what came back before the
   failure — this is the fastest way to tell "the driver sent the wrong
   command" apart from "the instrument replied with something unexpected."

## "I want every future failure on this bench to leave a diagnostic bundle automatically"

```robotframework
*** Settings ***
Library         rf_agilent34411a.Agilent34411ALibrary
Suite Setup     Connect    resource=${VISA_RESOURCE}
Suite Teardown  Teardown With Diagnostics

*** Keywords ***
Teardown With Diagnostics
    ${bundle}=    Export Diagnostic Bundle
    Log    Diagnostic bundle: ${bundle}    console=True
    Disconnect
```

(Robot's own suite-end hook still finalizes `run_summary.json`/
`evidence_manifest.json` after this — `Export Diagnostic Bundle` here
captures state a moment earlier in the same teardown, useful if `Disconnect`
itself is what's failing.)

## "Did this run actually touch real hardware?"

Check `execution_mode` in `run_summary.json`: `REAL_HARDWARE`, `SIMULATOR`,
or `MIXED` if the suite connected both a real and a simulated alias. See
`device_identity.json`'s per-alias `execution_mode` field to tell which
alias was which in a mixed run.

## "I just want to turn this off"

```robotframework
Library    rf_agilent34411a.Agilent34411ALibrary    evidence_enabled=${FALSE}
```

## Validating that a run directory wasn't tampered with or truncated

```console
python scripts/validate_evidence.py results/session/rf_agilent34411a/<run>/
```
