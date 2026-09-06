# Architecture: built on scpi-driver-core

This driver's infrastructure comes from
[`scpi-driver-core`](https://github.com/ami3go/scpi-driver-core). This page
records what moved, what stayed, and why.

## Layering

```text
        Robot keywords / pytest fixtures
                      |
              Agilent 33220A driver        device semantics, safety, verdicts
                      |
                 ScpiClient           SCPI framing, typed queries
                      |
              VisaTransport
```

Dependencies point downward only. Nothing in `scpi_driver_core` imports
`robot`, `hardpy`, or `pytest`, and nothing in it knows this instrument exists.

## What moved to the core

the hand-rolled PyVISA transport and the identity parsing.

## What stayed here

the modulation, sweep and burst behaviour, and the arbitrary-waveform handling.

The rule is the one from the core's task document: if code interprets the
physical behaviour of this instrument family, or contains its command tree, it
belongs in this package.

## Worth knowing

By this driver the migration was mechanical, because the seam and the core API had already been settled by the earlier ones. That compounding is the actual return on the work, not the line count of any single migration.

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
