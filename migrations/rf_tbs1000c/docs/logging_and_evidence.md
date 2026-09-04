# Logging and evidence (RFDS-008)

`rf_tbs1000c` records every public keyword call as structured evidence so a
failure can be diagnosed after the fact, without needing to reproduce it live
on the bench. This document describes what gets recorded, where it goes, and
how to read it. The implementation is `rf_tbs1000c/evidence.py`.

## What gets recorded, and where

One **run** covers one `Tbs1000cLibrary` instance's lifetime — not one
`Connect`/`Disconnect` pair, since this driver supports multiple
simultaneously connected oscilloscopes via the `alias` parameter and there is
no single "disconnect everything" keyword. The run is written to:

```text
results/session/rf_tbs1000c/<UTC timestamp>_<run_id>/
├── run_summary.json          # authoritative: final status, error/warning counts, duration
├── run_summary.md            # human-readable derived summary
├── environment.json          # Python/Robot/driver/pyvisa versions, sanitized host token
├── device_identity.json      # one entry per connected alias: model, resource, identity string
├── evidence_manifest.json    # one entry per artifact below, with a SHA-256 hash each
├── events/
│   ├── events.jsonl          # every lifecycle event (run start/finish, operation start/end)
│   ├── operations.jsonl      # one entry per keyword call: arguments, duration, result, status
│   └── errors.jsonl          # one entry per raised exception: category, message, traceback
├── protocol/
│   ├── exchanges.jsonl       # every SCPI command/query and response, machine-readable
│   ├── outbound_trace.log    # the same commands/queries, human-readable (driver -> instrument)
│   └── inbound_trace.log     # instrument -> driver (query responses; binary waveform blocks
│                              # are recorded as length + a short hash, not raw bytes)
└── integrity/
    └── checksums.sha256      # sha256sum-compatible list of every artifact above
```

Override the root with `RFDS_EVIDENCE_ROOT` (default `results`, relative to
the current working directory).

## How the SCPI trace works

`Connect` wraps the newly-opened session's transport in
`evidence.InstrumentedTransport`, which sits transparently between
`tbs1000c/driver.py` and the real `PyvisaUsbtmcTransport`/`SimulatedTransport`
— every `write()`/`query()`/`query_binary()`/`write_binary()` call is logged
before being forwarded unchanged. `driver.py` and `transport.py` are
untouched: SCPI construction, validation, and waveform decoding stay exactly
where the task specification says they belong (task §5.2).

## Reading a failure

1. Open `run_summary.json` — `final_status`, `error_count`, and
   `evidence_completeness` tell you whether to keep looking.
2. Open `events/errors.jsonl` — one JSON object per exception, each with a
   `category` (`VALIDATION`, `STATE`, `HARDWARE`, `PROTOCOL`, `ENVIRONMENT`,
   `ASSERTION`, or `UNKNOWN`), the exception type/message, and a full
   traceback.
3. Cross-reference `operation_id`/`correlation_id` from the error into
   `events/operations.jsonl` to see the exact keyword call (arguments
   included) that failed, and into `protocol/exchanges.jsonl` to see exactly
   which SCPI commands that operation had already sent before it failed.
4. `protocol/outbound_trace.log` gives a plain chronological read of every
   SCPI command/query this run sent — useful for "did it even send
   `TRIGger:A:EDGE:SOUrce`?" questions without parsing JSON.

Every event/operation/error carries a `correlation_id`: calls made *because
of* another call (for example `Measurement Should Be Within` calling `Get
Immediate Measurement`) share their parent's correlation ID, so one workflow's
full trace can be pulled out of the JSONL files with a single `grep`.

## Enabling/disabling it

On by default. Pass `evidence_enabled=${FALSE}` when importing the library to
disable it — errors still go to the standard Python logger and Robot's own
log either way, only the structured run directory is skipped:

```robotframework
Library    rf_tbs1000c.Tbs1000cLibrary    evidence_enabled=${FALSE}
```

## Exporting a diagnostic bundle

```robotframework
${path}=    Export Diagnostic Bundle
Log    Diagnostic bundle written to ${path}
```

Zips the run directory (with a freshly recomputed manifest) to a single file.
Works mid-session, before the suite ends — useful when troubleshooting
something that hasn't finished failing yet.

## When the run gets finalized

`run_summary.json`/`evidence_manifest.json` are written once, when the suite
ends — `Tbs1000cLibrary` already registers itself as a Robot listener
(`ROBOT_LIBRARY_LISTENER = self`) for best-effort session cleanup at suite
end (`_end_suite`); evidence finalization now happens there too. Outside
Robot Framework (plain Python/pytest use), call `library._end_suite(None,
{})` yourself, or reach into `library._evidence.finalize()` directly — see
`tests/evidence/test_evidence.py`.

## Simulation honesty (RFDS-008 §6.6)

`run_summary.json`'s `execution_mode` starts `UNKNOWN` and resolves as
sessions connect: `SIMULATOR` if every `Connect` in this run used
`simulated=${TRUE}`, `REAL_HARDWARE` if every one used a real USBTMC
resource, or `MIXED` if a run had both. Evidence from a `SIMULATOR`/`MIXED`
run is never silently presented as proof of real hardware behavior.

## What this system deliberately does not do

See `rf_phidget_relay/docs/logging_and_evidence.md` for the fuller rationale
(this engine was adapted from that one). In short: no shared cross-driver
package (none exists yet in this repository), no log rotation/backpressure
policy, no cryptographic signing/retention automation, and `category` in
`errors.jsonl` is a pragmatic mapping of `tbs1000c/exceptions.py`'s own
hierarchy rather than literal RFDS-007 codes (RFDS-007 wasn't available while
writing this).

## Validating a run's integrity

```console
python scripts/validate_evidence.py results/session/rf_tbs1000c/<run>/
```

Recomputes every SHA-256 hash in the manifest, checks every JSONL stream is
valid JSON with a gap-free monotonic `sequence`, and confirms
`run_summary.json` is present and internally consistent.
