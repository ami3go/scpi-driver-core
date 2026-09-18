# Acceptance criteria status

Against section 48 of `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`.
Last audited after the `0.1.0.dev4` test-harness expansion on `main` commit
`2c46b4fc55d79319ae17d7508308555db8a1decf`.

## Framework independence

- [x] no Robot Framework runtime dependency
- [x] no HardPy runtime dependency
- [x] no pytest runtime dependency
- [x] usable directly from plain Python

`pytest`, Hypothesis, pytest-timeout, and PyVISA-sim are development/test dependencies only.
The runtime package remains framework-independent.

## Transport

- [x] canonical boundary uses `bytes`
- [x] VISA backend implemented
- [x] Serial backend implemented
- [x] TCP backend implemented
- [x] UDP backend implemented
- [x] Mock/Scripted backend implemented
- [x] explicit transport state model
- [x] deterministic idempotent close
- [x] all I/O bounded
- [x] transaction serialization implemented

Applicable backends are exercised through reusable transport-contract tests. TCP/UDP also use
real local loopback endpoints; VISA has a PyVISA-sim end-to-end path.

## SCPI / IEEE-488.2

- [x] text codec implemented
- [x] `write()` and `query()` implemented
- [x] typed query helpers implemented
- [x] identity parser implemented
- [x] IEEE-488.2 helpers implemented
- [x] SCPI error queue implemented
- [x] definite-length binary block encode/decode implemented
- [x] arbitrary binary bytes preserved exactly

Protocol invariants and malformed/truncated cases have both deterministic regression tests and
Hypothesis property coverage.

## Runtime

- [x] named sessions
- [x] deterministic active session
- [x] list sessions
- [x] disconnect all
- [x] reconnect generation IDs
- [x] transport-open state separated from communication health
- [x] finite timeouts/deadlines
- [x] safe retry rules
- [x] bounded polling

Session/client lock ordering has a dedicated multithreaded pytest-timeout watchdog so a
deadlock regression fails in bounded time.

## Diagnostics

- [x] trace observer
- [x] OPEN/CLOSE/TX/RX/ERROR events
- [x] operation/session correlation
- [x] JSONL sink
- [x] redaction hook
- [x] command history in scripted simulation

## Test harness

- [x] deterministic pytest unit/regression suite
- [x] reusable transport conformance suite
- [x] Hypothesis property tests with separate `dev` and deterministic CI profiles
- [x] PyVISA-sim end-to-end integration through `VisaTransport`/PyVISA
- [x] local TCP/UDP socket integration without external endpoints
- [x] pytest-timeout per-test/session bounds
- [x] explicit short-bound concurrency/deadlock watchdog
- [x] `hardware` marker reserved for HIL and excluded from default CI
- [x] default CI requires no connected laboratory hardware

The detailed harness contract is documented in `docs/testing.md`, `tests/README.md`, and
`AGENTS.md`.

## Quality

- [x] meaningful coverage >= 90%
- [x] ruff passes
- [x] formatting check passes
- [x] mypy passes (strict)
- [x] wheel builds
- [x] sdist builds
- [x] `py.typed` included
- [x] CI passes on supported Python versions (3.10, 3.11, 3.12, 3.13)
- [x] full non-hardware harness passes on all supported Python versions

The `0.1.0.dev4` PR and post-merge `main` CI matrices both passed all four supported Python
versions, including the expanded hardware-free harness.

## Migration proof — NOT MET

- [ ] Agilent 34411A works through the core
- [ ] TBS1000C binary transfers work through the core
- [ ] N6700 VISA and TCP paths work through the core
- [ ] N83624 TCP/UDP/serial paths work through the core
- [ ] EA PS9000T works without EA-specific code in the core
- [ ] existing Robot adapters can call migrated drivers
- [ ] HardPy/pytest can call the same migrated drivers without Robot dependency

These require work in the concrete driver repositories and HIL evidence. Simulation and
hardware-free CI strengthen confidence in the generic core, but they do not establish real
instrument compatibility.

Each migrated concrete driver should reuse the layered test-harness approach described in
`docs/testing.md`: unit + scripted simulation + Hypothesis where useful + PyVISA-sim where
applicable + bounded pytest-timeout execution + separate HIL.

## Release status

**`v0.1.0` is not tagged.** The representative migration proof remains the release blocker.

The architecture has substantial hardware-free evidence: unit/regression tests, transport
contracts, Hypothesis-generated cases, scripted simulation, local TCP/UDP endpoints,
PyVISA-sim integration, and bounded concurrency tests. What remains intentionally unclaimed is
compatibility evidence from the representative real drivers/instruments. Until that work is
complete, the public API should still be treated as provisional because migrations may expose
a missing primitive or an abstraction that needs adjustment.
