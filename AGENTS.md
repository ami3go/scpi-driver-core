# AI Agent Guidance

This repository is intended to be reused by concrete Python SCPI instrument drivers. When an AI/code agent creates, migrates, or finishes a concrete driver that depends on `scpi-driver-core`, the final deliverable must include a layered test harness that reuses the testing stack already established here rather than inventing a parallel framework.

## Final driver test-harness requirement

Use the following tools as development/test dependencies where applicable:

- **pytest-timeout** — mandatory for automated driver test suites that can block on transport I/O, locks, worker threads, polling, or recovery paths. Every test run must have finite per-test and overall bounds. A hung instrument or deadlock must fail CI rather than stall it indefinitely.
- **Hypothesis** — use property-based testing for reusable input spaces such as SCPI parsers, command/value formatting, IEEE-488.2 binary blocks, malformed/truncated responses, boundaries, validators, retry/state behavior, and other logic where generated cases provide better coverage than a few hand-picked examples. CI profiles must be deterministic/reproducible enough for failures to be replayed and diagnosed.
- **PyVISA-sim** — for drivers that use `VisaTransport`/PyVISA and whose relevant SCPI behavior can be represented by PyVISA-sim, add an integration layer that exercises the real path `concrete driver -> scpi-driver-core -> VisaTransport -> PyVISA -> PyVISA-sim`. At minimum, cover identity/communication plus representative read and write operations for the device.

These packages remain **test/development dependencies only**. Do not add them to the runtime dependency surface of a concrete driver unless the driver has an independent runtime reason to require them.

## Required layered strategy

A final production-oriented driver should normally contain these layers:

1. **Unit tests** — parsers, validation, limits, command construction, device-specific semantics, and failure translation.
2. **`ScriptedScpiTransport` / mock tests** — deterministic protocol scenarios, malformed replies, timeouts, disconnects, SCPI error queues, retry/recovery behavior, and exact command verification.
3. **Hypothesis tests** — property/boundary testing where generated inputs are useful.
4. **PyVISA-sim integration tests** — when the driver supports VISA and the simulated behavior is representable.
5. **Hardware/HIL tests** — separate tests for behavior that requires a real instrument, especially vendor quirks, binary transfers, timing, protection behavior, and device state transitions.

PyVISA-sim is not a replacement for `ScriptedScpiTransport`, and neither simulator is a replacement for HIL evidence. Each layer tests a different failure surface.

## CI rules for generated drivers

- Default CI must not require physical hardware or an external laboratory endpoint.
- Tests that require hardware must be explicitly marked and excluded from normal CI unless a dedicated HIL runner is configured.
- Do not hide flaky or hanging tests with blanket reruns. Fix deterministic failures and retain finite timeout guards.
- Prefer exercising public driver APIs and the real `scpi-driver-core` stack. Do not mock internal core implementation details unless isolation is specifically required by the test.
- Keep expected SCPI command/response fixtures close to the concrete driver so vendor/model behavior remains outside `scpi-driver-core`.
- Preserve and reuse the core transport/session/retry/error semantics instead of reimplementing them in the driver test harness.

## Completion checklist for an AI/code agent

Before declaring a concrete driver complete, verify that:

- the normal pytest suite has finite timeout protection;
- suitable parser/framing/validation logic has property tests where beneficial;
- VISA drivers have PyVISA-sim coverage where technically feasible;
- the scripted/mock simulator covers communication failures and malformed responses that PyVISA-sim cannot express conveniently;
- hardware-specific cases are clearly separated and documented;
- the driver is tested through its public Python API, not only by calling low-level SCPI helpers directly;
- CI passes without connected laboratory hardware;
- runtime code does not import `pytest`, `hypothesis`, `pytest_timeout`, or `pyvisa_sim`.

If one of these layers is not applicable to a particular driver, document the reason in that driver's test documentation rather than silently omitting it.
