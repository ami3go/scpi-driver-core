# Logging and evidence (RFDS-008)

`rf_ea_ps9000t` records every public keyword call, and every raw SCPI
command/response, as structured evidence so a failure can be diagnosed after
the fact without needing to reproduce it live. This document describes what
gets recorded, where it goes, and how to read it. The implementation is
`rf_ea_ps9000t/evidence.py`.

## Per-alias runs

This library supports multiple concurrently-connected named power supplies
(the `alias` parameter accepted by every keyword). Evidence is tracked **per
alias**: each `Connect` call starts its own evidence run, and each
`Disconnect` finalizes and closes only that alias's run. A keyword called
with no active alias yet (rare — e.g. `Get Active Power Supply` before any
`Connect`) falls back to a shared `"__unbound__"` bucket run that is never
explicitly finalized (it still has raw JSONL evidence, just no
`run_summary.json`/manifest, unless `Export Diagnostic Bundle` is called on
it directly).

## What gets recorded, and where

```text
results/session/rf_ea_ps9000t/<UTC timestamp>_<run_id>/
├── run_summary.json          # authoritative: final status, error/warning counts, duration
├── run_summary.md            # human-readable derived summary
├── environment.json          # Python/Robot/driver/pyvisa versions, sanitized host token
├── device_identity.json      # manufacturer, resource, transport type, *IDN? — after Connect
├── evidence_manifest.json    # one entry per artifact below, with a SHA-256 hash each
├── events/
│   ├── events.jsonl          # every lifecycle event (run start/finish, operation start/end)
│   ├── operations.jsonl      # one entry per keyword call: arguments, duration, result, status
│   └── errors.jsonl          # one entry per raised exception: category, message, traceback
├── protocol/
│   ├── exchanges.jsonl       # every SCPI command/response, machine-readable
│   ├── outbound_trace.log    # the same commands, human-readable (driver -> device)
│   └── inbound_trace.log     # raw device responses (device -> driver)
└── integrity/
    └── checksums.sha256      # sha256sum-compatible list of every artifact above
```

Override the root with the `RFDS_EVIDENCE_ROOT` environment variable (default
`results`, relative to the current working directory).

## Reading a failure

1. Open `run_summary.json` — `final_status`, `error_count`, and
   `evidence_completeness` tell you whether to keep looking.
2. Open `events/errors.jsonl` — one JSON object per exception, each with a
   `category` (`VALIDATION`, `STATE`, `HARDWARE`, or `UNKNOWN`), the exception
   type/message, and a full traceback.
3. Cross-reference `operation_id`/`correlation_id` from the error into
   `events/operations.jsonl` to see the exact keyword call (arguments
   included, and which `alias`/`session_alias`) that failed, and into
   `protocol/exchanges.jsonl` to see the exact SCPI commands and responses
   that operation exchanged before it failed.
4. `protocol/outbound_trace.log`/`inbound_trace.log` give a plain
   chronological read of every SCPI command sent and every raw response
   received — useful for "did it even send `VOLTage 12.0`?" questions
   without parsing JSON.

Every event/operation/error also carries a `correlation_id`: calls made
*because of* another call share their parent's correlation ID, so you can
pull one workflow's full trace out of the JSONL files with a single `grep`.

## Known gap: the initial remote-control acquisition isn't traced

`TracingTransport` wraps `driver.transport` *after* `Connect` returns from
`EaPs9000T.connect_visa`/`connect_simulated`, so the SCPI exchange for
`acquire_remote_control()` — sent inside those classmethods, before the
wrapper exists — isn't captured at the byte level. The `Connect` operation
record itself (in `operations.jsonl`) still covers it: arguments, duration,
and success/failure (including a raised `EaPs9000TConnectionError` if remote
control was refused). See `evidence.py`'s `TracingTransport` docstring for
why this trade-off was made instead of duplicating connection-construction
logic in the RF adapter.

## Enabling/disabling it

Evidence recording is on by default. Construct the library with
`evidence_enabled=${FALSE}` to disable it — errors still go to the standard
Python logger (and Robot's own log) either way, only the structured run
directory is skipped:

```robotframework
Library    rf_ea_ps9000t.EaPs9000TLibrary    evidence_enabled=${FALSE}
```

## Exporting a diagnostic bundle

Call `Export Diagnostic Bundle` (optionally with an `alias`) to zip the
current run — including a freshly recomputed manifest — to a single file:

```robotframework
${path}=    Export Diagnostic Bundle    alias=bench
Log    Diagnostic bundle written to ${path}
```

Works mid-session, before `Disconnect` — useful when troubleshooting
something that hasn't finished failing yet.

## Simulator honesty (RFDS-008 §6.6)

`run_summary.json`'s `execution_mode` is `REAL_HARDWARE` for a VISA
connection and `SIMULATOR` for `Connect simulated=${TRUE}` (this driver ships
a real protocol-level simulator, `ea_ps9000t/simulator.py`, that parses
actual SCPI text — not a Python-level test double — hence `SIMULATOR` rather
than `FAKE`). Evidence from a `SIMULATOR` run is never silently presented as
proof of real hardware behavior.

## What this system deliberately does not do

RFDS-008 describes a platform-wide evidence standard; this driver implements
the parts of it that make a concrete troubleshooting difference and
intentionally does not implement:

- **A shared cross-driver package.** No such package exists yet in this
  repository (see `AI_Guides/RFDS-008...md` §35), so `evidence.py` here is
  self-contained, adapted from the same pattern built for `rf_phidget_relay`
  and `rf_agilent33220a`/`rf_agilent34411a`/etc.
- **Log rotation / backpressure policy** (§34) — this driver's event volume
  per session is small enough that it isn't needed.
- **Cryptographic signing, retention/archival automation, crash-recovery
  tooling** (§30.4, §31.2, §32) — out of scope for a single driver package.
- **RFDS-007 error codes** — RFDS-007 wasn't available while writing this;
  `category` in `errors.jsonl` is a pragmatic mapping of this driver's own
  exception hierarchy (`ea_ps9000t/exceptions.py`), not literal RFDS-007 codes.

## Validating a run's integrity

`scripts/validate_evidence.py` (with `.sh`/`.bat`/`.ps1` wrappers) recomputes
every SHA-256 hash in a run's `evidence_manifest.json`, checks every JSONL
stream is valid JSON with a gap-free monotonic `sequence`, and confirms
`run_summary.json` exists and is internally consistent:

```console
python scripts/validate_evidence.py results/session/rf_ea_ps9000t/<run>/
```
