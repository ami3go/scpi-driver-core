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

## Waiting out a slow command

This instrument can take a long time over a command, and a `*OPC?` poll issued
while it is busy may get no answer at all. That interacts badly with the rule
above: a query whose reply never arrived costs the connection, because the
reply may still turn up and would be read as the answer to the next question.
The old `wait_operation_complete` polled in a tight loop and so destroyed the
session on its first slow command.

It now treats a poll that times out as "not finished yet" and reopens the
transport before the next one. Reopening is what makes the stale reply
harmless: TCP and RS232 get a fresh stream, and a new UDP socket has a new
local port, so a late datagram is dropped rather than mistaken for a reading.
The interval backs off, and the method still returns `False` at its deadline
rather than raising, so a long operation cannot take the process down:

```python
if not driver.wait_operation_complete(timeout=300.0):
    ...  # still running; the session is open, so ask the instrument why
```

`*CLS` and `*ESR?` are undocumented on this instrument and stay gated behind
`experimental_ok`, so the core's `Ieee4882.wait_for_completion` — which polls
the event status register instead — is not used here.

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
- `test_slow_operations.py` covers the completion wait above against an
  emulator that refuses to answer, on an injected clock so the suite stays
  fast: the poll schedule, the reopen, and the bounded `False` return.

Unlike the six VISA migrations this driver has no `test_api_conformance.py`.
The shared harness needs a constructor it can call with no arguments, and this
driver is built around a transport that must be supplied.
