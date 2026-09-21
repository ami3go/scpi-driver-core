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

**Reads are explicitly bounded by the core API.** `ReadRequest` rejects unbounded
combinations and fields the selected `ReadMode` would ignore. Transport reads/writes,
protocol waits, retries, polling and flush/drain paths use finite call-level bounds. One
platform limitation remains outside Python's portable cancellation control: blocking OS name
resolution may exceed a requested socket connect deadline. Applications that require a hard
end-to-end connection deadline should resolve/cache addresses before entering the critical
operation or isolate resolution in a separately bounded process/thread policy.

**An uncertain timeout invalidates the connection by default.** Once a request may have
reached an instrument, a late reply must not be mistaken for the answer to a later command.
TCP, UDP, serial, VISA, mock and scripted transports therefore use the faulting profile by
default. Backend-specific recovery mechanisms such as VISA Device Clear are explicit opt-in
capabilities rather than side effects of an ordinary timeout.

**Transport state is not communication health.** `is_open` reports resource ownership and
never performs device I/O. State introspection does not wait behind a long instrument I/O
operation. Instrument responsiveness is tracked separately by `SessionHealth`, which is also
updated by normal client traffic.

**VISA buffer flush is not Device Clear.** `VisaTransport.flush()` only discards local VISA
buffers through `viFlush`-style operations and never calls `viClear`. Destructive Device
Clear is exposed explicitly as `device_clear()` on transports that support it.

**VISA manager lifetime is application-wide.** PyVISA may return the same ResourceManager
for a library to multiple callers. `VisaTransport` therefore treats managers as borrowed,
even when it requested one itself, and closes only the resource it opened.

**Nothing is retried unless the caller classifies it as safe.** Repeating an instrument
operation can mean a second trigger, output-enable, calibration command, or other physical
side effect. Writes are therefore not automatically replayed. Retry recovery is permitted
only from a transport-fault state; deliberately closed sessions are never silently reopened.

**Parsers reject rather than coerce.** Generic numeric parsing accepts ASCII SCPI decimal
syntax, preserves exact integral values through `Decimal`, and maps the standard SCPI
`9.9E37` / `-9.9E37` / `9.91E37` special values to Inf/NaN semantics. Device-specific
sentinels outside the SCPI standard remain the concrete driver's responsibility.

**Error-queue reads are explicit policy.** Reading `SYST:ERR?` is itself instrument traffic
and consumes state, so automatic checking is opt-in. Binary block operations obey the same
configured policy as text operations. A failed operation is not automatically followed by an
error-queue drain when the stream may already be invalid; recover safely first, then inspect
if the instrument/procedure requires it.

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

Normal CI runs every layer above HIL on Python 3.10 through 3.13 and requires >=90% branch
coverage. Physical-hardware tests use the `hardware` marker and are excluded from the default
gate. Simulation demonstrates software semantics; it is not evidence for physical bus
behavior, vendor VISA implementation details, serial control-line glitches, protection
behavior, or real-instrument timing.

The detailed rationale, commands, and requirements for generated/migrated drivers are in
`docs/testing.md`, `tests/README.md`, and `AGENTS.md`. The 2026-09-21 runtime-integrity review
and the disposition of all 38 findings are recorded in
`docs/deep-review-2026-09-21-disposition.md`.

## What belongs in a concrete driver

Command trees, measurement semantics, channel maps, output-enable and arming policy,
calibration procedures, safe shutdown, range/capability rules, and every pass/fail verdict.
If code interprets the physical behavior of one instrument family, it does not belong in the
core.

The core supplies mechanisms for safety—finite operation bounds, connection invalidation,
confirmation guards, typed errors, deterministic cleanup—but not bench safety policy. None of
it replaces hardware interlocks, fuses, emergency stops, protection circuitry, or a wiring
review.

## Project status

The generic architecture and hardware-free validation stack are implemented. The remaining
`v0.1.0` blocker is representative migration/HIL proof across the target driver families.
Until those migrations are complete, the public API remains provisional because real driver
migration is expected to expose any missing generic primitive.

## Reference

- Getting started, installation, and project status: top-level `README.md`
- Test-harness architecture: `docs/testing.md`
- Acceptance status and evidence boundaries: `docs/acceptance.md`
- 2026-09-21 deep-review disposition: `docs/deep-review-2026-09-21-disposition.md`
- Runnable examples: `examples/`
- Test-suite layout and transport-backend guidance: `tests/README.md`
- AI/code-agent requirements: `AGENTS.md`
- Contribution and quality gates: `CONTRIBUTING.md`
- Detailed original architecture/acceptance specification: `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`
