# Architecture: built on scpi-driver-core

This driver's infrastructure comes from
[`scpi-driver-core`](https://github.com/ami3go/scpi-driver-core). This page
records what moved, what stayed, and why.

## Layering

```text
        Robot keywords / pytest fixtures
                      |
              NGI N83624 driver        device semantics, safety, verdicts
                      |
                 ScpiClient           SCPI framing, typed queries
                      |
              TcpTransport, UdpTransport and SerialTransport
```

Dependencies point downward only. Nothing in `scpi_driver_core` imports
`robot`, `hardpy`, or `pytest`, and nothing in it knows this instrument exists.

## What moved to the core

three hand-rolled backends: TCP, UDP and RS232.

## What stayed here

the UDP port scheme where 7001 to 7024 map to channels 1 to 24, the TCP port range check, and the RS232 baudrate whitelist.

The rule is the one from the core's task document: if code interprets the
physical behaviour of this instrument family, or contains its command tree, it
belongs in this package.

## Worth knowing

The core faults a TCP transport when a read times out, which makes data buffered before the timeout unreachable. This driver returned whatever had arrived if the terminator never came, so its read now accumulates incrementally to preserve that behaviour.

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
