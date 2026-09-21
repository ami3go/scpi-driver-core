# Acceptance criteria status

Against section 48 of `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`.
Last audited for the `0.1.0.dev6` runtime-integrity hardening after the
2026-09-21 deep review of `main@241d4b6`.

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
- [x] transport and protocol I/O paths use finite call-level bounds
- [x] uncertain timeouts/interruptions invalidate the connection by default
- [x] transaction serialization implemented
- [x] multi-step protocol operations have transport-level serialization/invalidation
- [x] state/introspection does not wait behind long I/O

The finite-bound claim applies to operations controlled by this package. Blocking OS name
resolution is a platform service and cannot be portably pre-empted by the synchronous Python
socket API; applications needing a hard end-to-end connect bound should pre-resolve/cache
addresses or isolate resolution behind their own cancellation boundary.

Applicable backends are exercised through reusable transport-contract tests. TCP/UDP also use
real local loopback endpoints; VISA has a PyVISA-sim end-to-end path. Simulation proves the
software contract, not the behavior of a particular VISA vendor, serial adapter, or physical
instrument.

## SCPI / IEEE-488.2

- [x] text codec implemented
- [x] embedded CR/LF command injection rejected for text commands/string data
- [x] `write()` and `query()` implemented
- [x] typed query helpers implemented
- [x] strict ASCII numeric parsing with exact integral conversion
- [x] standard SCPI Inf/NaN sentinel handling
- [x] identity parser implemented
- [x] IEEE-488.2 helpers implemented
- [x] optional VISA Device Clear/serial poll/bus trigger/local-control capabilities
- [x] SCPI error queue implemented with structured partial-drain diagnostics
- [x] definite-length binary block encode/decode implemented
- [x] binary-block operations are transport-atomic and use configured error policy
- [x] malformed/partial block reads invalidate the connection
- [x] arbitrary binary bytes preserved exactly

Protocol invariants and malformed/truncated cases have both deterministic regression tests and
Hypothesis property coverage. Physical-bus behavior of Device Clear, serial poll, trigger,
REN/local control and END/EOI remains HIL evidence rather than a simulator claim.

## Runtime

- [x] named sessions
- [x] deterministic active session
- [x] registry/session alias integrity enforced
- [x] list sessions
- [x] disconnect all
- [x] context-manager cleanup
- [x] reconnect generation IDs
- [x] transport-open state separated from communication health
- [x] normal client traffic updates session health
- [x] recovery only reopens FAULTED sessions
- [x] recovery re-applies configured probe/identity validation
- [x] safe retry rules
- [x] recovery failures consume retry attempts when retryable
- [x] retry backoff is overflow-safe and does not hold the client lock while sleeping
- [x] bounded polling

Session/client lock ordering and confirmation-guard concurrency have dedicated
pytest-timeout/watchdog coverage so a deadlock regression fails in bounded time.

## Diagnostics

- [x] trace observer
- [x] OPEN/CLOSE/TX/RX/ERROR events
- [x] operation/session correlation
- [x] per-transport trace context when one tracer is shared by several sessions
- [x] failed transactions never log an uncertain command as successful TX
- [x] JSONL sink
- [x] payload-limit validation and optional per-event fsync
- [x] redaction hook
- [x] undecodable payloads cannot silently bypass configured redaction
- [x] response redaction can use originating command context
- [x] observer failures are counted/logged rather than silently losing audit data
- [x] command history in scripted simulation

## Test harness

- [x] deterministic pytest unit/regression suite
- [x] reusable transport conformance suite
- [x] Hypothesis property tests with separate `dev` and deterministic CI profiles
- [x] PyVISA-sim end-to-end integration through `VisaTransport`/PyVISA
- [x] local TCP/UDP socket integration without external endpoints
- [x] default mock/scripted timeout profile matches faulting hardware semantics
- [x] pytest-timeout per-test/session bounds
- [x] explicit short-bound concurrency/deadlock watchdogs
- [x] `hardware` marker reserved for HIL and excluded from default CI
- [x] default CI requires no connected laboratory hardware

The detailed harness contract is documented in `docs/testing.md`, `tests/README.md`, and
`AGENTS.md`.

## Quality

- [x] meaningful branch coverage >= 90%
- [x] ruff passes
- [x] formatting check passes
- [x] mypy passes (strict)
- [x] wheel builds
- [x] sdist builds
- [x] `py.typed` included
- [x] CI passes on supported Python versions (3.10, 3.11, 3.12, 3.13)
- [x] full non-hardware harness passes on all supported Python versions

The `0.1.0.dev6` review-hardening PR has a fully green four-version matrix, including the
hardware-free harness and the package build on Python 3.13. The exact review disposition and
remaining HIL-only verification are recorded in `docs/deep-review-2026-09-21-disposition.md`.

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

Specific HIL work still required by the deep review includes representative VISA local flush
versus Device Clear behavior, END/EOI/vendor VISA behavior, serial control-line/handshake
behavior, and bus-level clear/poll/trigger/local-control semantics.

Each migrated concrete driver should reuse the layered test-harness approach described in
`docs/testing.md`: unit + scripted simulation + Hypothesis where useful + PyVISA-sim where
applicable + bounded pytest-timeout execution + separate HIL.

## Release status

**`v0.1.0` is not tagged.** The representative migration proof remains the release blocker.

The architecture has substantial hardware-free evidence: unit/regression tests, transport
contracts, Hypothesis-generated cases, scripted simulation, local TCP/UDP endpoints,
PyVISA-sim integration, and bounded concurrency tests. What remains intentionally unclaimed is
compatibility evidence from representative real drivers/instruments and vendor-specific
physical-bus behavior. Until that work is complete, the public API should still be treated as
provisional because migrations may expose a missing primitive or an abstraction that needs
adjustment.
