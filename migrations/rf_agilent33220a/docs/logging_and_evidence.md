# Logging and evidence (RFDS-008)

`rf_agilent33220a` records every public keyword call as structured evidence so
a failure can be diagnosed after the fact, without needing to reproduce it
live against real hardware. This document describes what gets recorded,
where it goes, and how to read it. The implementation is
`rf_agilent33220a/evidence.py`.

## What gets recorded, and where

One evidence **run** covers the whole suite (`ROBOT_LIBRARY_SCOPE = "SUITE"`
— one `Agilent33220ALibrary` instance persists for the suite's lifetime, and
may connect/disconnect several aliased generators over that time), written
to:

```text
results/session/rf_agilent33220a/<UTC timestamp>_<run_id>/
├── run_summary.json          # authoritative: final status, error/warning counts, execution mode
├── run_summary.md            # human-readable derived summary
├── environment.json          # Python/Robot/driver versions, sanitized host token
├── device_identity.json      # one entry per connected alias: resource, transport, identity
├── evidence_manifest.json    # one entry per artifact below, with a SHA-256 hash each
├── events/
│   ├── events.jsonl          # every lifecycle event (run start/finish, operation start/end)
│   ├── operations.jsonl      # one entry per keyword call: arguments, duration, result, status
│   └── errors.jsonl          # one entry per raised exception: category, message, traceback
├── protocol/
│   ├── exchanges.jsonl       # every SCPI command/query/response, machine-readable
│   ├── outbound_trace.log    # the same commands, human-readable (driver -> instrument)
│   └── inbound_trace.log     # instrument -> driver (query responses)
└── integrity/
    └── checksums.sha256      # sha256sum-compatible list of every artifact above
```

Override the root with `RFDS_EVIDENCE_ROOT` (default `results`, relative to
the current working directory).

## SCPI protocol tracing

Unlike a vendor-SDK-only driver, this instrument is SCPI-over-VISA with a
single `Transport.write()`/`Transport.query()` boundary
(`agilent33220a/transport.py`). `evidence.TracingTransport` wraps whichever
real transport (`PyvisaTransport` or `SimulatedTransport`) a connection uses,
transparently to the core driver, and logs every command and response
through that one seam — so `protocol/outbound_trace.log` is a literal,
chronological SCPI command log (`*IDN?`, `FREQuency 1000.0`, `VOLTage?`, ...)
you can read directly, and every entry is correlated (via `operation_id`) to
the exact keyword call that issued it.

## Multiple generators, one run

`Connect`'s `alias` parameter lets one suite drive several generators. Every
operation, protocol exchange, and device-identity entry records its
`session_alias`, so `grep '"session_alias": "bench2"' events/operations.jsonl`
isolates one generator's activity within a run that touched several.

## Simulation honesty (RFDS-008 §6.6)

`run_summary.json`'s `execution_mode` starts `NO_HARDWARE` and is upgraded as
`Connect` calls happen: all-`simulated=${TRUE}` connections -> `SIMULATOR`,
all-real -> `REAL_HARDWARE`, a mix (e.g. one bench alias real, one simulated
for comparison) -> `MIXED`. It never defaults to claiming real hardware.

## Reading a failure

1. Open `run_summary.json` — `final_status`, `error_count`, and
   `execution_mode` tell you whether to keep looking and whether this was
   even a real-hardware run.
2. Open `events/errors.jsonl` — one JSON object per exception, each with a
   `category` (`VALIDATION`, `STATE`, `HARDWARE`, `ENVIRONMENT`, `UNKNOWN`),
   the exception type/message, and a full traceback.
3. Cross-reference `operation_id`/`correlation_id` into
   `events/operations.jsonl` for the exact keyword call (arguments included)
   that failed, and into `protocol/exchanges.jsonl` for the exact SCPI
   commands that operation had already sent before it failed.

## Enabling/disabling it

On by default. Pass `evidence_enabled=${FALSE}` to disable it — errors still
reach Robot's own log and the standard Python logger either way:

```robotframework
Library    rf_agilent33220a.Agilent33220ALibrary    evidence_enabled=${FALSE}
```

## Exporting a diagnostic bundle

```robotframework
${path}=    Export Diagnostic Bundle
Log    Diagnostic bundle written to ${path}
```

Zips the run's current state (refreshing the manifest first) without
finalizing it — usable mid-suite, before the run ends.

## What this system deliberately does not do

See `rf_phidget_relay/docs/logging_and_evidence.md` for the general rationale
(same project, same deliberate-scope list): no shared cross-driver evidence
package exists yet in this repository, so this is a self-contained,
per-driver module rather than an imported common library; no log
rotation/backpressure policy, cryptographic signing, retention automation, or
literal RFDS-007 error codes (RFDS-007 wasn't available while writing this —
`category` in `errors.jsonl` is a pragmatic mapping of
`agilent33220a/exceptions.py`'s own hierarchy).

## Validating a run's integrity

```console
python scripts/validate_evidence.py results/session/rf_agilent33220a/<run>/
```

Recomputes every SHA-256 hash, checks every JSONL stream is valid JSON with a
gap-free monotonic `sequence`, and confirms `run_summary.json` is internally
consistent.
