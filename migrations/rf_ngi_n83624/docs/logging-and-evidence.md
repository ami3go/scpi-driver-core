# Logging and evidence (RFDS-008)

`rf_ngi_n83624` records every public keyword call as structured evidence so a
failure can be diagnosed after the fact, without needing to reproduce it live
on the bench. This document describes what gets recorded, where it goes, and
how to read it. The implementation is `rf_ngi_n83624/evidence.py`.

## Relationship to the existing audit log

This driver already has a lightweight, opt-in JSONL audit log: pass
`audit_log_path=...` to any `Open N83624 * Connection` keyword and every
safety-relevant action (arm/disarm, output on/off, mode changes, connection
open/close, raw SCPI) is appended as one JSON line via
`NGI_N83624._audit_for`. It has no correlation IDs, no protocol trace, and no
integrity hashing, and it's off unless you ask for it.

The evidence system described here is a separate, deeper layer, **on by
default**: every public keyword call becomes a correlated operation record
(arguments, duration, result/failure) plus a protocol trace of the actual
SCPI write/query traffic, written per connection alias to
`results/session/rf_ngi_n83624/<run>/` with a SHA-256-hashed manifest. The
two systems are independent — both can be active for the same session.

## One run per connection alias

This library supports multiple simultaneous named connections
(`ROBOT_LIBRARY_SCOPE = "GLOBAL"`), so evidence is scoped the same way: one
**run** per alias, created when that alias is first used (usually at `Open
N83624 * Connection`) and finalized — `run_summary.json` and
`evidence_manifest.json` written — when that alias's session actually closes
(`Close N83624 Connection` or `Close All N83624 Connections`, which calls the
former once per alias internally).

```text
results/session/rf_ngi_n83624/<UTC timestamp>_<run_id>/
├── run_summary.json          # authoritative: final status, error/warning counts, duration
├── run_summary.md            # human-readable derived summary
├── environment.json          # Python/Robot/driver versions, sanitized host token
├── device_identity.json      # manufacturer, model, *IDN? response, transport, resource
├── evidence_manifest.json    # one entry per artifact below, with a SHA-256 hash each
├── events/
│   ├── events.jsonl          # every lifecycle event (run start/finish, operation start/end)
│   ├── operations.jsonl      # one entry per keyword call: arguments, duration, result, status
│   └── errors.jsonl          # one entry per raised exception: category, message, traceback
├── protocol/
│   ├── exchanges.jsonl       # every SCPI write/query, machine-readable
│   ├── outbound_trace.log    # the same commands, human-readable (driver -> instrument)
│   └── inbound_trace.log     # instrument -> driver (query responses)
└── integrity/
    └── checksums.sha256      # sha256sum-compatible list of every artifact above
```

Override the root with the `RFDS_EVIDENCE_ROOT` environment variable (default
`results`, relative to the current working directory).

## How protocol tracing works

`ngi_n83624.driver.N83624CellSimulator` has an optional
`protocol_observer` attribute — a `(direction, text)` callback invoked for
every SCPI write and query, added specifically so this framework-layer
evidence engine can observe the wire protocol without the core driver
package knowing anything about RFDS-008, evidence, or Robot Framework. The
Robot adapter (`rf_ngi_n83624/library.py`) wires it to the relevant alias's
`EvidenceRun.log_protocol` when a connection opens. If you use
`ngi_n83624.driver.N83624CellSimulator` directly from Python (bypassing
Robot Framework entirely), you can set `.protocol_observer` yourself to
capture the same trace.

## Reading a failure

1. Open `run_summary.json` — `final_status`, `error_count`, and
   `evidence_completeness` tell you whether to keep looking.
2. Open `events/errors.jsonl` — one JSON object per exception, each with a
   `category` (`VALIDATION`, `STATE`, `HARDWARE`, `ASSERTION`, or `UNKNOWN` —
   a pragmatic mapping of this driver's own exception hierarchy, not literal
   RFDS-007 codes, since RFDS-007 wasn't available while writing this), the
   exception type/message, and a full traceback.
3. Cross-reference `operation_id`/`correlation_id` from the error into
   `events/operations.jsonl` to see the exact keyword call (arguments
   included) that failed, and into `protocol/exchanges.jsonl` to see what
   SCPI commands that operation had already sent before it failed.
4. `protocol/outbound_trace.log` gives a plain chronological read of every
   SCPI command this run sent — useful for "did it even try to arm channel
   5?" questions without parsing JSON.

Every event/operation/error also carries a `correlation_id`: calls made
*because of* another call (e.g. `Close All N83624 Connections` calling
`Close N83624 Connection` once per alias) share their parent's correlation
ID, so you can pull one workflow's full trace out of the JSONL files with a
single `grep`.

## Enabling/disabling it

Evidence recording is on by default. Pass `evidence_enabled=${FALSE}` when
importing the library to disable it — errors still go to the standard Python
logger (and Robot's own log) either way, only the structured run directory is
skipped:

```robotframework
Library    rf_ngi_n83624.NGI_N83624Library    evidence_enabled=${FALSE}
```

## Exporting a diagnostic bundle

Call the `Export Diagnostic Bundle` keyword (or
`EvidenceRun.export_diagnostic_bundle()` directly in Python) to zip a given
alias's current run — including a freshly recomputed manifest — to a single
file for attaching to a bug report:

```robotframework
${path}=    Export Diagnostic Bundle    alias=bench
Log    Diagnostic bundle written to ${path}
```

This works mid-session, before the connection closes — useful when
troubleshooting something that hasn't finished failing yet.

## Simulation honesty (RFDS-008 §6.6)

`run_summary.json`'s `execution_mode` is `REAL_HARDWARE` for TCP/UDP/serial
sessions and `SIMULATOR` for `Open N83624 Emulator` sessions — determined
from which keyword actually created the alias, not guessed later. Evidence
from a `SIMULATOR` run is never silently presented as proof of real
hardware behavior.

## What this system deliberately does not do

RFDS-008 describes a platform-wide evidence standard; this driver implements
the parts of it that make a concrete troubleshooting difference and
intentionally does not implement:

- **A shared cross-driver package.** No such package exists yet in this
  repository (see `AI_Guides/RFDS-008...md` §35), so `evidence.py` here is
  self-contained. Other drivers in this repository that adopt the same
  pattern each carry their own adapted copy.
- **Log rotation / backpressure policy** (§34) — this driver's event volume
  per session is small enough that it isn't needed.
- **Cryptographic signing, retention/archival automation, crash-recovery
  tooling** (§30.4, §31.2, §32) — out of scope for a single driver package.

## Validating a run's integrity

`scripts/validate_evidence.py` (with `.sh`/`.bat`/`.ps1` wrappers) recomputes
every SHA-256 hash in a run's `evidence_manifest.json`, checks every JSONL
stream is valid JSON with a gap-free monotonic `sequence`, and confirms
`run_summary.json` exists and is internally consistent:

```console
python scripts/validate_evidence.py results/session/rf_ngi_n83624/<run>/
```
