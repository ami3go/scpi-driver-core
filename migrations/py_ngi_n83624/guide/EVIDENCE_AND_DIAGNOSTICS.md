# Guide: diagnosing a failed N83624 test run

A short, task-oriented companion to `docs/logging-and-evidence.md` (which
describes the evidence system itself). This guide walks through the
situations that actually come up on a bench.

## "A test failed and I wasn't watching — what happened?"

1. Ask whoever ran it for the evidence run directory for the alias that
   failed (`results/session/rf_ngi_n83624/<run>/`), or for the zip from
   `Export Diagnostic Bundle` if they called it.
2. Open `run_summary.md` first — it's the one-paragraph version.
3. Open `events/errors.jsonl`. Each line is one exception; find the one whose
   `capability` matches the keyword Robot reported as failing.
4. Note its `operation_id`. Search `events/operations.jsonl` for that ID to
   see the exact arguments Robot passed in.
5. Search `protocol/exchanges.jsonl` for the same `operation_id` to see
   exactly which SCPI commands that keyword sent before failing — this tells
   you whether the failure was in argument validation (no SCPI traffic
   logged) or partway through a compound operation like `Configure Source
   Mode` (some but not all commands logged).

## "I want every future failure on this bench to leave a diagnostic bundle automatically"

Add `Export Diagnostic Bundle` to suite teardown, guarded so it always runs
even after a failure:

```robotframework
*** Settings ***
Library         rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${FALSE}
Suite Setup     Open N83624 TCP Connection    bench    host=192.168.0.123
Suite Teardown  Teardown With Diagnostics

*** Keywords ***
Teardown With Diagnostics
    Run Keyword And Ignore Error    All N83624 Outputs Off    alias=bench
    ${bundle}=    Export Diagnostic Bundle    alias=bench
    Log    Diagnostic bundle: ${bundle}    console=True
    Close N83624 Connection    bench
```

The bundle path is logged to the console and to Robot's own `log.html`, so
whoever triages the run doesn't need bench access — just the zip.

## "Which alias does a given evidence run belong to?"

Every record's `session_alias` field says which connection alias produced
it — check `run_summary.json`'s `device_identity_reference` /
`device_identity.json` for the `*IDN?` response and resource (host:port or
serial port) that alias was actually talking to, in case the bench had more
than one instrument or a re-pointed IP address at the time.

## "Did this run actually touch real hardware?"

Check `execution_mode` in `run_summary.json` (also shown in
`run_summary.md`): `REAL_HARDWARE` for TCP/UDP/serial connections, or
`SIMULATOR` for `Open N83624 Emulator` sessions. See RFDS-008 §6.6
("simulation honesty") for why this is recorded explicitly rather than left
to be inferred.

## "I just want to turn this off"

```robotframework
Library    rf_ngi_n83624.NGI_N83624Library    evidence_enabled=${FALSE}
```

Nothing gets written to `results/`. Exceptions still reach Robot's own log,
the standard Python logger, and (if you set `audit_log_path`) the existing
opt-in audit log — you lose the structured, correlated record, not the error
itself.

## Validating that a run directory wasn't tampered with or truncated

```console
python scripts/validate_evidence.py results/session/rf_ngi_n83624/<run>/
```

Reports any hash mismatch, missing file, or JSONL stream with a gap or
duplicate in its `sequence` numbers. Exit code is non-zero on any finding.
