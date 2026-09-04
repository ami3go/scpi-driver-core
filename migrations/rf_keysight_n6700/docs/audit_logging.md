# Audit Logging

Every SCPI write and query passes through `N6700.write_scpi()` /
`N6700.query_scpi()` in `keysight_n6700/driver.py`, which is the single
transport-boundary choke point for this driver — every typed keyword
(`Set N6700 Voltage`, `Turn On N6700 Output`, ...) and every raw
`Query N6700 SCPI` call routes through one of these two methods, so enabling
audit logging captures the complete command/response history for a session,
not just a curated subset.

## Enabling it

Pass `audit_log_path` when connecting:

```robotframework
Connect To N6700    USB0::0x0957::0x0907::MY43014421::INSTR    main
...    audit_log_path=${OUTPUT DIR}/n6700_audit.jsonl
```

or from Python:

```python
from keysight_n6700 import N6700

n6700 = N6700(audit_log_path="n6700_audit.jsonl")
```

`audit_log_path` is `None` by default — audit logging is opt-in and has no
effect on driver behavior when omitted, only on what gets written to that
file.

## What gets recorded

`N6700._append_protocol_trace()` appends one JSON object per line
(`.jsonl` — one record per SCPI transaction) to `audit_log_path`:

```json
{
  "timestamp_iso": "2026-08-06T10:15:30.123456+00:00",
  "timestamp_unix": 1785000930.123456,
  "operation": "query",
  "command": "MEAS:VOLT? (@1)",
  "response": "5.001200E+00",
  "error": null,
  "duration_s": 0.041823
}
```

- `operation` is `"write"` or `"query"`.
- `response` is `null` for writes (SCPI commands don't return a value) and
  for failed queries.
- `error` is `null` on success, otherwise `"<ExceptionType>: <message>"` —
  the transaction is logged whether it succeeded or failed, so a partial or
  aborted session still leaves a usable trail up to the point of failure.
- The file is opened in append mode and flushed per line; killing the process
  mid-session loses at most the one in-flight transaction, not the log.

Separately, higher-level operations (multi-channel configuration calls,
shutdown sequences) can be recorded as a single `keysight_n6700.types.AuditRecord`
via `N6700.audit()` — a coarser-grained "what did this one operation do"
record (requested values, every SCPI command/response it issued, duration,
resulting output states) rather than the raw per-transaction stream. Both use
the same `audit_log_path` file.

## Reading a troubleshooting log

Each line is independent JSON, so standard line-oriented tools work directly:

```console
# Every failed transaction in the session
grep '"error": *"[^n]' n6700_audit.jsonl

# Everything sent to/read from channel 1's voltage/current queries
grep 'VOLT\|CURR' n6700_audit.jsonl

# Slowest transactions (helpful for diagnosing a flaky USB/VISA link)
python -c "
import json
records = [json.loads(l) for l in open('n6700_audit.jsonl')]
for r in sorted(records, key=lambda r: -r['duration_s'])[:10]:
    print(r['duration_s'], r['operation'], r['command'])
"
```

Because every record carries `timestamp_unix` and `duration_s`, this log is
also the right place to look first for "did the instrument actually receive
this command, and how long did it take to respond" questions — the kind
Robot's own `log.html` doesn't answer once a suite has more than a few dozen
keyword calls.

## Relationship to the RFDS-019 conformance evidence

The `audit_log_path` mechanism above is a lightweight, always-available,
opt-in trace for any session (interactive Python use, an ad hoc Robot suite,
a one-off script). It is distinct from — and a good complement to — the much
more structured evidence produced by the RFDS-019 real-hardware self-check
(see [N6775A self-check](n6775a_self_check.md)): that run additionally
produces `keyword_inventory.json`/`.yaml`, `protocol_vector_results.json`,
`keyword_coverage.csv`, `exclusions.json`, environment/device identity, and a
Markdown summary under `results/call_protocol_conformance/keysight_n6700/<UTC
timestamp>/`, per driver/protocol conformance vector rather than per raw SCPI
transaction. Use `audit_log_path` when you want a trace of one specific
session; use the self-check when you want proof every public keyword still
reaches the instrument correctly.

## What this does not do

There is currently no built-in integrity manifest (SHA-256 hashes) or
automatic redaction pass over `audit_log_path` files, and no keyword to zip
one up for sharing — unlike the RFDS-019 self-check's evidence bundle, an
audit log you enable yourself is a plain file you're responsible for handling
(this driver has no credential-bearing SCPI commands to redact in the first
place, so that gap is lower-risk than it would be for, e.g., a
network-connected instrument with authentication).
