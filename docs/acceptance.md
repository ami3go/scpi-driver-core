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

## Migration proof

Carried out on the `phase15-driver-migration` branch, against
`ami3go/RobotFrameworks_hw_drivers` at commit `a5388c5`. See
`migrations/README.md`.

- [x] Agilent 34411A works through the core
- [x] TBS1000C binary transfers work through the core
- [x] N6700 VISA and TCP paths work through the core
- [x] N83624 TCP/UDP/serial paths work through the core
- [x] EA PS9000T works without EA-specific code in the core
- [x] existing Robot adapters can call migrated drivers
- [x] HardPy/pytest can call the same migrated drivers without Robot dependency

All five representative drivers, plus two secondary ones, keep their own test
suites passing unchanged, and each has migration-proof tests that drive the
real transport over the core. No vendor identifier appears anywhere under
`src/scpi_driver_core/`, checked by grep for every migrated manufacturer and
model.

The last two items hold because each driver's Robot library is unchanged and
its Robot tests still pass, while the device layers import no `robot` at all,
so the same driver is callable from a plain pytest fixture.

## Release status

**`v0.1.0` is still not tagged**, for one remaining reason rather than seven.

Section 42's secondary validation also lists the E-Resistor SCPI path and the
BK8500B SCPI-facing path. Those are not migrated yet. Everything section 48
enumerates is now met, so this is a judgement call rather than a hard gate: the
architecture has been demonstrated by seven drivers across VISA, USBTMC, raw
TCP, UDP and RS232, which is more than section 42 requires.

What a migration cannot show is behaviour against real hardware. Every result
here is against fakes and loopback sockets. The five instrument-specific
findings recorded in `migrations/README.md` — VISA terminations trimming binary
blocks, unbounded socket reads, fault-on-timeout losing buffered data — were
all found by migration rather than by the core's own tests, which is a fair
warning that hardware would find more.
