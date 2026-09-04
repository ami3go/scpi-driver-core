# Logging and evidence (RFDS-008)

`rf_agilent34411a` records every public keyword call as structured evidence so
a failure can be diagnosed after the fact, without needing to reproduce it
live. This document describes what gets recorded, where it goes, and how to
read it. Implementation: `rf_agilent34411a/evidence.py`.

## Why

This driver is `ROBOT_LIBRARY_SCOPE = "SUITE"` and supports multiple
simultaneous named connections (`Connect ... alias=B`). A structured record
of exactly which alias sent which SCPI command, in what order, is easier to
debug a cross-talk or wrong-instrument bug from than console output alone.

## What gets recorded, and where

One evidence **run** covers the whole suite (one `Agilent34411ALibrary`
instance, from its first keyword call until Robot's own suite-end hook
fires), written to:

```text
results/session/rf_agilent34411a/<UTC timestamp>_<run_id>/
├── run_summary.json          # authoritative: final status, error/warning counts, duration
├── run_summary.md            # human-readable derived summary
├── environment.json          # Python/Robot/driver versions, sanitized host token
├── device_identity.json      # one entry per alias: manufacturer/model/serial/firmware
├── evidence_manifest.json    # one entry per artifact below, with a SHA-256 hash each
├── events/
│   ├── events.jsonl          # every lifecycle event (run start/finish, operation start/end)
│   ├── operations.jsonl      # one entry per keyword call: alias, arguments, duration, result, status
│   └── errors.jsonl          # one entry per raised exception: category, message, traceback
├── protocol/
│   ├── exchanges.jsonl       # every SCPI command/response, machine-readable, tagged by alias
│   ├── outbound_trace.log    # the same commands, human-readable (driver -> instrument)
│   └── inbound_trace.log     # instrument -> driver (raw response text)
└── integrity/
    └── checksums.sha256      # sha256sum-compatible list of every artifact above
```

Override the root with `RFDS_EVIDENCE_ROOT` (default `results`, relative to
the current working directory).

## Reading a failure

1. `run_summary.json` — `final_status`, `error_count`, `evidence_completeness`.
2. `events/errors.jsonl` — one JSON object per exception: `category`
   (`VALIDATION`, `CONNECTION`, `TIMEOUT`, `PROTOCOL`, `DEVICE`,
   `OUT_OF_RANGE`, or `UNKNOWN`), exception type/message, full traceback, and
   which `session_alias` it happened on.
3. Cross-reference `operation_id`/`correlation_id` into `events/operations.jsonl`
   for the exact keyword call (arguments included), and into
   `protocol/exchanges.jsonl` for the exact SCPI commands that operation sent
   and the raw responses it got back before failing.
4. `protocol/outbound_trace.log` / `inbound_trace.log` give a plain
   chronological read of every SCPI exchange this run made, across every
   alias — useful for "did it even send `FUNC VOLT:AC`?" questions without
   parsing JSON.

Nested keyword calls (rare in this driver, but e.g. any keyword that reads
back a value it just set) share their parent's `correlation_id`, so one
logical workflow's full trace can be pulled from the JSONL files with a
single `grep`.

## Multi-alias runs

Every operation, error, and protocol exchange record carries `session_alias`.
`device_identity.json` has one entry per alias under `sessions`. A run's
`execution_mode` is `REAL_HARDWARE` if every connected alias was real
hardware, `SIMULATOR` if every alias used `simulated=${TRUE}`, and `MIXED` if
a run connected both — never silently reported as one or the other (RFDS-008
§6.6 simulation honesty).

## Enabling/disabling it

On by default. Disable with:

```robotframework
Library    rf_agilent34411a.Agilent34411ALibrary    evidence_enabled=${FALSE}
```

Errors still reach Robot's own log and the standard Python logger either way
— only the structured run directory is skipped.

## Exporting a diagnostic bundle

```robotframework
${path}=    Export Diagnostic Bundle
Log    Diagnostic bundle written to ${path}
```

Refreshes the manifest and zips the run's current state — works mid-suite,
before the suite ends, and does not finalize the run.

## What this system deliberately does not do

See `rf_phidget_relay/docs/logging_and_evidence.md`'s equivalent section —
the same scope decisions apply here: no shared cross-driver package (none
exists yet in this repository; this module was adapted from
`rf_phidget_relay/rf_phidget_relay/evidence.py`, with SCPI/multi-alias
specifics replacing the Phidget-SDK/single-session ones), no log
rotation/backpressure policy, no crypto signing/retention automation, and
`errors.jsonl`'s `category` field is a pragmatic mapping of this driver's own
`agilent34411a/exceptions.py` hierarchy rather than literal RFDS-007 codes
(RFDS-007 wasn't available while writing this).

## Validating a run's integrity

```console
python scripts/validate_evidence.py results/session/rf_agilent34411a/<run>/
```

Recomputes every SHA-256 hash in the manifest, checks every JSONL stream is
valid JSON with a gap-free monotonic `sequence`, and confirms
`run_summary.json` is internally consistent.
