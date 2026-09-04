# Documentation

`scpi-driver-core` is the shared infrastructure under a set of SCPI instrument
drivers. It provides transports, SCPI framing, parsing, sessions, and tracing.
It contains no device semantics.

## Layering

```text
        concrete driver          device semantics, safety policy, verdicts
              |
        ScpiSession              alias, lifetime, health, identity cache
              |
        ScpiClient               framing, typed queries, one execution choke point
              |
        Transport                bytes: VISA, serial, TCP, UDP, mock, scripted
```

Dependencies point downward only. Nothing under `src/scpi_driver_core/` imports
`robot`, `hardpy`, or `pytest`, so the same concrete driver runs unchanged from
Robot Framework, a pytest fixture, a notebook, or a script.

## The decisions worth knowing

**The transport boundary is bytes, not text.** A `str` boundary cannot carry a
waveform capture or an arbitrary-waveform upload. Text framing lives one layer
up, in `ScpiTextCodec`.

**Reads are always bounded.** `ReadRequest` rejects any combination of fields
that would permit an unbounded read, and rejects fields the chosen `ReadMode`
would ignore, so a request never reads differently from the way it looks.

**Transport state is not communication health.** `is_open` reports whether a
resource is held and never performs I/O. Whether the instrument answers is
`SessionHealth.communication_ok`, which is tri-state: `None` means nobody has
asked. A powered-down instrument on a live TCP connection is open and mute.

**Nothing is retried unless you say so.** Repeating a write can mean a second
trigger or a second output-enable. `ScpiClient.write` has no retry parameter,
and `query` refuses a retrying policy unless the caller marks that query
`ReplayPolicy.SAFE`.

**Parsers reject rather than coerce.** A malformed value raises with the
response attached; it never becomes a silent zero. Device-specific overload
sentinels stay in the driver.

**The error queue is never drained behind your back.** Reading it is instrument
traffic and it clears entries you may want. Opt in with `ScpiExecutionPolicy`.

**Redaction rewrites the recorded bytes.** Redacting only the decoded text would
leak the secret the moment a sink persisted the payload.

## What belongs in a concrete driver

Command trees, measurement semantics, channel maps, output-enable and arming
policy, calibration procedures, safe shutdown, and every pass/fail verdict. If
code interprets the physical behavior of one instrument family, it does not
belong here.

The core supplies mechanisms for safety — finite timeouts, confirmation guards,
typed errors, deterministic cleanup — but not policy. None of it replaces
hardware interlocks, fuses, emergency stops, or a wiring review.

## Reference

- Getting started and installation: the top-level `README.md`
- Runnable examples: `examples/`
- Adding a transport backend: `tests/README.md`
- Full architecture and acceptance criteria: `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`
