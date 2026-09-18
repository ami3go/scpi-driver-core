# Documentation

`scpi-driver-core` is shared infrastructure for SCPI instrument drivers. It provides
transports, SCPI framing/parsing, execution helpers, sessions, tracing, deterministic
simulation, and the common test-harness primitives used by concrete driver packages. It
contains no manufacturer- or model-specific device semantics.

## Layering

```text
        concrete driver          device semantics, safety policy, verdicts
              |
        ScpiSession              alias, lifetime, health, identity cache
              |
        ScpiClient               framing, typed queries, execution policy
              |
        Transport                bytes: VISA, serial, TCP, UDP, mock, scripted
```

Dependencies point downward only. Nothing under `src/scpi_driver_core/` imports `robot`,
`hardpy`, or `pytest`, so the same concrete driver can run unchanged from Robot Framework,
a pytest fixture, a notebook, a CLI, or a normal Python application.

## Core design decisions

**The transport boundary is bytes, not text.** A `str` boundary cannot safely carry
waveforms, arbitrary-waveform uploads, setup files, or arbitrary binary payloads. Text
framing therefore lives one layer up in `ScpiTextCodec`.

**Reads are always bounded.** `ReadRequest` rejects unbounded combinations and rejects
fields the chosen `ReadMode` would ignore. A request should never behave differently from
how it reads in code.

**Transport state is not communication health.** `is_open` reports resource ownership and
never performs I/O. Instrument responsiveness is tracked separately by
`SessionHealth.communication_ok`.

**Nothing is retried unless the caller classifies it as safe.** Repeating an instrument
operation can mean a second trigger, output-enable, calibration command, or other physical
side effect. Writes are therefore not automatically replayed.

**Parsers reject rather than coerce.** Malformed values raise typed errors with the
original response attached. Instrument-specific sentinels remain the responsibility of the
concrete driver.

**Error-queue reads are explicit policy.** Reading `SYST:ERR?` is itself instrument traffic
and consumes state, so automatic checking is opt-in.

**Generic abstractions require demonstrated reuse.** The project intentionally prefers
small explicit concrete-driver methods over speculative descriptor/property frameworks.
Shared abstractions should be extracted only when multiple real drivers demonstrate the same
need.

## Validation architecture

The package uses a layered test strategy because each layer covers a different failure
surface:

```text
unit tests
   |
transport contract
   |
Hypothesis properties
   |
scripted simulator + local socket integration
   |
PyVISA-sim end-to-end integration
   |
pytest-timeout concurrency/hang watchdogs
   |
hardware/HIL evidence in concrete driver repositories
```

Normal CI runs every layer above HIL on Python 3.10 through 3.13 and requires >=90% coverage.
Physical-hardware tests use the `hardware` marker and are excluded from the default gate.

The detailed rationale, commands, and requirements for generated/migrated drivers are in
`docs/testing.md`, `tests/README.md`, and `AGENTS.md`.

## What belongs in a concrete driver

Command trees, measurement semantics, channel maps, output-enable and arming policy,
calibration procedures, safe shutdown, range/capability rules, and every pass/fail verdict.
If code interprets the physical behavior of one instrument family, it does not belong in the
core.

The core supplies mechanisms for safety—finite timeouts, confirmation guards, typed errors,
deterministic cleanup—but not bench safety policy. None of it replaces hardware interlocks,
fuses, emergency stops, protection circuitry, or a wiring review.

## Project status

The generic architecture and hardware-free validation stack are implemented. The remaining
`v0.1.0` blocker is representative migration/HIL proof across the target driver families.
Until those migrations are complete, the public API remains provisional because real driver
migration is expected to expose any missing generic primitive.

## Reference

- Getting started, installation, and project status: top-level `README.md`
- Test-harness architecture: `docs/testing.md`
- Acceptance status: `docs/acceptance.md`
- Runnable examples: `examples/`
- Test-suite layout and transport-backend guidance: `tests/README.md`
- AI/code-agent requirements: `AGENTS.md`
- Contribution and quality gates: `CONTRIBUTING.md`
- Detailed original architecture/acceptance specification: `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`
