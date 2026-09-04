# Acceptance criteria status

Against section 48 of `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`.
Last audited at commit `0857b98`.

## Framework independence

- [x] no Robot Framework runtime dependency
- [x] no HardPy runtime dependency
- [x] no pytest runtime dependency
- [x] usable directly from plain Python

Verified by grep over `src/` and by importing the package with none of the
three installed. `pytest` is a dev dependency only.

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

Every backend passes the same conformance suite in `tests/transport_contract/`.
The serialization test was checked against a variant with the lock removed and
fails there, so it discriminates.

## SCPI / IEEE-488.2

- [x] text codec implemented
- [x] `write()` and `query()` implemented
- [x] typed query helpers implemented
- [x] identity parser implemented
- [x] IEEE-488.2 helpers implemented
- [x] SCPI error queue implemented
- [x] definite-length binary block encode/decode implemented
- [x] arbitrary binary bytes preserved exactly

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

## Diagnostics

- [x] trace observer
- [x] OPEN/CLOSE/TX/RX/ERROR events
- [x] operation/session correlation
- [x] JSONL sink
- [x] redaction hook
- [x] command history in scripted simulation

## Quality

- [x] meaningful unit coverage >= 90% (96%)
- [x] ruff passes
- [x] formatting check passes
- [x] mypy passes (strict)
- [x] wheel builds
- [x] sdist builds
- [x] `py.typed` included
- [x] CI passes on supported Python versions (3.10, 3.11, 3.12, 3.13)

## Migration proof — NOT MET

- [ ] Agilent 34411A works through the core
- [ ] TBS1000C binary transfers work through the core
- [ ] N6700 VISA and TCP paths work through the core
- [ ] N83624 TCP/UDP/serial paths work through the core
- [ ] EA PS9000T works without EA-specific code in the core
- [ ] existing Robot adapters can call migrated drivers
- [ ] HardPy/pytest can call the same migrated drivers without Robot dependency

These require the driver sources in `ami3go/RobotFrameworks_hw_drivers`, which
are not part of this repository. Phase 15 cannot be carried out here, so none
of these can be claimed.

## Release status

**`v0.1.0` is not tagged.** Section 47 permits the tag only once the acceptance
criteria are met, and the migration-proof section is not. Everything else is
complete and verified.

The architecture has been exercised only against the scripted simulator and the
conformance suite. That is real evidence, but it is not the evidence section 42
asks for: five representative drivers migrated without manufacturer-specific
code leaking into the core. Until that happens the public API should be treated
as provisional, since a migration is exactly the thing likely to reveal a
missing primitive.
