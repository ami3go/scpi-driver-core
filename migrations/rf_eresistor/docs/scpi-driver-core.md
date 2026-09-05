# Architecture: built on scpi-driver-core

This driver's infrastructure comes from
[`scpi-driver-core`](https://github.com/ami3go/scpi-driver-core). This page
records what moved, what stayed, and why.

## Layering

```text
        Robot keywords / pytest fixtures
                      |
              E-Resistor driver        device semantics, safety, verdicts
                      |
                 ScpiClient           SCPI framing, typed queries
                      |
              TcpTransport
```

Dependencies point downward only. Nothing in `scpi_driver_core` imports
`robot`, `hardpy`, or `pytest`, and nothing in it knows this instrument exists.

## What moved to the core

the byte-at-a-time recv(1) loop, replaced by one bounded read that also enforces the response size limit.

## What stayed here

the connection-state machine, the reconnect backoff, the multi-line framing, and this instrument's own ERR-prefixed error format.

The rule is the one from the core's task document: if code interprets the
physical behaviour of this instrument family, or contains its command tree, it
belongs in this package.

## Worth knowing

Only the SCPI path was migrated. The HTTP fallback in http_api.py is device-specific and untouched. The greeting read needed care: an instrument that sends no banner is normal, so a timeout there must not break the connection.

## Guarantees the core adds

- **Bounded reads.** Every read declares how it ends and how large it may get.
  There is no unbounded receive loop in the transport layer.
- **Byte fidelity.** SCPI framing removes only the terminator it was configured
  with, never a generic `strip()`, so whitespace and null bytes inside a payload
  survive.
- **An explicit transport state model.** `close()` is idempotent and always
  releases the resource; I/O while not open fails before anything is
  transmitted; a failure leaving session validity uncertain faults the transport
  rather than being retried blindly.
- **Nothing retried by default.** Repeating a write can mean a second trigger or
  a second output-enable, so retries must be asked for explicitly.
- **Tracing.** Any transport can be wrapped to emit a JSONL protocol audit, with
  redaction hooks for calibration codes and other secrets.

## Testing

The driver's own suite is unchanged and still passes. Two additions live
alongside it:

- `test_core_migration.py` drives the real transport over the core against a
  fake backend or loopback server, because the pre-existing tests all use the
  simulator and so prove nothing about the transport that was replaced.
- `test_api_conformance.py` walks the whole public surface: it checks a snapshot
  so a rename or removal fails, and invokes every no-argument method against the
  simulator.

The conformance sweep only ever drives the simulator. It must never be pointed
at a real instrument, where blindly invoking every method would enable outputs.
