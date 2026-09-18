# AI Agent Guidance

This repository is intended to be reused by concrete Python SCPI instrument drivers. When an
AI/code agent creates, migrates, or finishes a concrete driver that depends on
`scpi-driver-core`, the final deliverable must reuse the test strategy already established
here rather than inventing a parallel framework.

The reference implementation of that strategy is documented in `docs/testing.md` and
`tests/README.md` and is exercised by this repository's normal CI.

## Prefer explicit driver code over speculative abstraction

AI-generated code removes much of the cost of repetitive, straightforward getters/setters.
Do not introduce a generic parameter/descriptor DSL merely to reduce boilerplate.

Prefer explicit methods when they make device behavior easier to audit:

```python
def set_voltage(self, value: float) -> None:
    self._limits.validate_voltage(value)
    self.session.client.write(f"VOLT {value:.6g}")


def get_voltage(self) -> float:
    return self.session.client.query_float("VOLT?")
```

A new abstraction belongs in `scpi-driver-core` only when multiple real drivers demonstrate a
shared requirement that cannot be served cleanly by the existing primitives. Examples of
credible reasons are common transport/session behavior, protocol parsing, reusable validation,
or tooling that needs shared metadata. Line-count reduction alone is not sufficient.

Complex procedures, instrument quirks, safety behavior, channel semantics, calibration, and
state transitions remain ordinary concrete-driver methods.

## Final driver test-harness requirement

Use the following tools as development/test dependencies where applicable:

- **pytest-timeout** — mandatory for automated driver suites that can block on transport I/O,
  locks, worker threads, polling, or recovery paths. Every run must have finite per-test and
  overall bounds. A hung instrument or deadlock must fail CI rather than stall it.
- **Hypothesis** — use property-based testing for reusable input spaces such as parsers,
  command/value formatting, IEEE-488.2 binary blocks, malformed/truncated responses,
  boundaries, validators, retry/state behavior, and other logic where generated cases provide
  better coverage than a few hand-picked examples.
- **PyVISA-sim** — for drivers using `VisaTransport`/PyVISA, add integration coverage where
  relevant behavior can be represented. Exercise the real path
  `concrete driver -> scpi-driver-core -> VisaTransport -> PyVISA -> PyVISA-sim`.

These packages remain **test/development dependencies only** unless a concrete driver has an
independent runtime reason to require one.

## Required layered strategy

A production-oriented concrete driver should normally contain these layers:

1. **Unit tests** — parsers, validation, limits, command construction, device-specific
   semantics, and failure translation.
2. **`ScriptedScpiTransport` / mock tests** — deterministic protocol scenarios, malformed
   replies, timeouts, disconnects, SCPI error queues, retry/recovery behavior, binary fixtures,
   and exact command verification.
3. **Hypothesis tests** — generated property/boundary tests where an input space has useful
   invariants.
4. **PyVISA-sim integration tests** — when VISA is supported and the relevant behavior is
   representable.
5. **Hardware/HIL tests** — separate tests for behavior requiring a real instrument, especially
   vendor quirks, binary transfers, timing, protection behavior, calibration, and physical
   state transitions.

PyVISA-sim is not a replacement for `ScriptedScpiTransport`, and neither simulator is a
replacement for HIL evidence. Each layer tests a different failure surface.

## Reuse the reference harness

Before creating new test infrastructure, inspect the existing reference implementation:

```text
tests/conftest.py
tests/property/
tests/integration/test_pyvisa_sim.py
tests/integration/fixtures/pyvisa_sim.yaml
tests/integration/test_timeout_watchdog.py
tests/transport_contract/
docs/testing.md
```

Adapt these patterns to the concrete driver rather than duplicating core transport/session
logic in the driver test suite.

For VISA drivers, test through the public concrete-driver API whenever possible rather than
proving only that low-level `ScpiClient` calls work.

## CI rules for generated drivers

- Default CI must not require physical hardware or an external laboratory endpoint.
- Tests requiring hardware must be explicitly marked and excluded from normal CI unless a
  dedicated HIL runner is configured.
- Use finite pytest-timeout bounds for the automated suite.
- Do not hide flaky or hanging tests with blanket reruns.
- Prefer public driver APIs and the real `scpi-driver-core` stack over mocks of internal core
  implementation details.
- Keep expected SCPI command/response fixtures close to the concrete driver so vendor/model
  behavior remains outside `scpi-driver-core`.
- Preserve and reuse core transport/session/retry/error semantics instead of reimplementing
  them in the driver harness.
- Keep test-only packages out of runtime dependencies.

## Completion checklist for an AI/code agent

Before declaring a concrete driver complete, verify that:

- the normal pytest suite has finite timeout protection;
- suitable parser/framing/validation logic has property tests where beneficial;
- VISA drivers have PyVISA-sim coverage where technically feasible;
- scripted/mock simulation covers communication failures and malformed responses that
  PyVISA-sim cannot express conveniently;
- hardware-specific cases are clearly separated and documented;
- the driver is tested through its public Python API, not only by low-level SCPI helpers;
- CI passes without connected laboratory hardware;
- runtime code does not import `pytest`, `hypothesis`, `pytest_timeout`, or `pyvisa_sim`;
- new generic abstractions have demonstrated reuse and are not present merely to reduce
  AI-generated boilerplate.

If one of these layers is not applicable to a particular driver, document the reason in that
driver's test documentation rather than silently omitting it.
