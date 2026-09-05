# Logging and evidence (RFDS-008)

`rf_eresistor` records every public keyword call as structured evidence so a
failure can be diagnosed after the fact, without needing to reproduce it live.
This document describes what gets recorded, where it goes, and how to read
it. The implementation is `rf_eresistor/evidence.py`.

## Relationship to the existing audit log

`eresistor_driver` already ships a framework-agnostic audit facility
(`AuditLogger`, in `eresistor_driver/logging_utils.py`), enabled via the
`audit_log_file` constructor/profile argument. It writes one JSON line per
*state-changing* SCPI command to a plain file and is unaffected by anything
in this document — it keeps working exactly as before, including when used
outside Robot Framework (`eresistor_driver/cli.py`).

The RFDS-008 evidence engine described here is a deeper, Robot-Framework-side
complementary layer: it traces *every* SCPI exchange (not only state-changing
ones) and every HTTP call (`Ping EResistor`, `Identify EResistor`, and the
calibration-download keywords use HTTP, not SCPI), correlates them with the
exact keyword invocation and arguments that caused them, and produces
integrity-checked, machine-validated evidence for troubleshooting one test
run. It does not read or duplicate the audit log file.

## What gets recorded, and where

Each **session** (one `EResistorLibrary` instance, from its first keyword
call until `Disconnect From EResistor` returns) is one **run**, written to:

```text
results/session/rf_eresistor/<UTC timestamp>_<run_id>/
├── run_summary.json          # authoritative: final status, error/warning counts, duration
├── run_summary.md            # human-readable derived summary
├── environment.json          # Python/Robot/driver versions, sanitized host token
├── device_identity.json      # identity, host, serial, firmware — written after Connect To EResistor
├── evidence_manifest.json    # one entry per artifact below, with a SHA-256 hash each
├── events/
│   ├── events.jsonl          # every lifecycle event (run start/finish, operation start/end)
│   ├── operations.jsonl      # one entry per keyword call: arguments, duration, result, status
│   └── errors.jsonl          # one entry per raised exception: category, message, traceback
├── protocol/
│   ├── exchanges.jsonl       # every SCPI/HTTP exchange, machine-readable
│   ├── outbound_trace.log    # the same exchanges, human-readable (driver -> device)
│   └── inbound_trace.log     # device -> driver (SCPI responses, HTTP bodies)
└── integrity/
    └── checksums.sha256      # sha256sum-compatible list of every artifact above
```

Override the root with the `RFDS_EVIDENCE_ROOT` environment variable (default
`results`, relative to the current working directory).

## Reading a failure

1. Open `run_summary.json` — `final_status`, `error_count`, and
   `evidence_completeness` tell you whether to keep looking.
2. Open `events/errors.jsonl` — one JSON object per exception, each with a
   `category` (`VALIDATION`, `STATE`, `HARDWARE`, `ASSERTION`, or `UNKNOWN`),
   the exception type/message, and a full traceback.
3. Cross-reference `operation_id`/`correlation_id` from the error into
   `events/operations.jsonl` to see the exact keyword call (arguments
   included) that failed, and into `protocol/exchanges.jsonl` to see what
   SCPI/HTTP exchanges that operation had already made before it failed.
4. `protocol/outbound_trace.log` gives a plain chronological read of every
   SCPI command and HTTP request this run made — useful for "did it even
   send `RES:SET`?" questions without parsing JSON.

Every event/operation/error also carries a `correlation_id`: calls made
*because of* another call (e.g. `Set EResistor Resistance` internally
querying calibration, or the generic `Disconnect` calling the underlying
`Disconnect From EResistor`) share their parent's correlation ID, so you can
pull one workflow's full trace out of the JSONL files with a single `grep`.

## Enabling/disabling it

On by default. Pass `evidence_enabled=${FALSE}` on the `Library` import to
disable it — errors still go to the standard Python logger (and Robot's own
log, and `AuditLogger` if configured) either way, only the structured run
directory is skipped:

```robotframework
Library    rf_eresistor.EResistorLibrary    host=192.168.0.55    evidence_enabled=${FALSE}
```

`session_alias` (default `default`) tags every record from a given library
instance.

## Exporting a diagnostic bundle

```robotframework
${path}=    Export Diagnostic Bundle
Log    Diagnostic bundle written to ${path}
```

Zips the current run — including a freshly recomputed manifest — to a single
file, mid-session, before `Disconnect From EResistor`. Useful when
troubleshooting something that hasn't finished failing yet.

## Simulation honesty (RFDS-008 §6.6)

`run_summary.json`'s `execution_mode` is `REAL_HARDWARE` for every run
against this driver's public API today — there is no bundled simulator, so
unit tests use a hand-rolled `FakeClient` set directly on `lib._client`,
bypassing `connect()` (and therefore bypassing protocol tracing and
`execution_mode` detection entirely). If a simulator or injectable transport
is added later, this field should be wired to reflect it honestly, the same
way `rf_phidget_relay`'s evidence engine distinguishes `FAKE` from
`REAL_HARDWARE` based on whether a test double was supplied.

## What this system deliberately does not do

See `AI_Guides/RFDS-008...md` for the full platform-wide standard. This
driver implements the parts of it that make a concrete troubleshooting
difference and intentionally does not implement a shared cross-driver
package (none exists yet in this repository), log rotation/backpressure
policy, cryptographic signing, retention/archival automation, or literal
RFDS-007 error codes (RFDS-007 wasn't available while writing this;
`category` in `errors.jsonl` is a pragmatic mapping of this driver's own
exception hierarchy).

## Validating a run's integrity

```console
python scripts/validate_evidence.py results/session/rf_eresistor/<run>/
```

Recomputes every SHA-256 hash in the manifest, checks every JSONL stream is
valid JSON with a gap-free monotonic `sequence`, and confirms
`run_summary.json` exists and is internally consistent.
