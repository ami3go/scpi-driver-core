# Test harness architecture

This document is the canonical description of the `scpi-driver-core` validation stack and
the baseline expected from concrete drivers that depend on it.

The objective is not to maximize the number of test frameworks. Each layer exists because it
covers a different class of failure, and normal CI must remain independent of physical
laboratory hardware.

## Layered harness

| Layer | Primary tool | Typical coverage |
| --- | --- | --- |
| Unit | pytest | command construction, parsers, validators, state, errors, tracing |
| Transport conformance | pytest | lifecycle, bounded reads, faults, close/reopen, transaction serialization |
| Property testing | Hypothesis | protocol invariants, malformed/truncated data, bounds, formatting, retry schedules |
| Deterministic instrument simulation | `ScriptedScpiTransport` | exact SCPI traffic, error queues, timeouts, disconnects, malformed responses |
| VISA integration | PyVISA-sim | concrete/real VISA stack without hardware |
| Local network integration | loopback TCP/UDP | real socket behavior without external endpoints |
| Concurrency watchdog | pytest-timeout | deadlocks, blocked workers, runaway polling/recovery paths |
| Hardware/HIL | pytest `hardware` marker | vendor quirks, timing, binary transfers, protection behavior, physical state changes |

No one layer is a substitute for the others. In particular, PyVISA-sim does not replace the
scripted simulator, and neither simulator replaces HIL evidence.

## Installed development tools

The repository's `dev` extra includes:

```text
pytest
pytest-cov
pytest-timeout
hypothesis
pyvisa-sim
mypy
ruff
build
```

Install the complete development environment with:

```bash
python -m pip install -e ".[dev,all]"
```

These are development/test dependencies. Runtime code must not import `pytest`, `hypothesis`,
`pytest_timeout`, or `pyvisa_sim`.

## Timeout policy

`pytest-timeout` provides a repository-wide finite bound:

```text
per test: 30 s
whole session: 600 s
```

Tests aimed specifically at lock ordering or deadlock regressions should use a shorter local
`@pytest.mark.timeout(...)` limit. A blocked transport, thread, polling loop, or recovery path
must fail CI rather than hang it.

Timeout guards are not a substitute for application-level timeout handling. Production code
must still use finite transport and operation deadlines.

## Hypothesis policy

Property tests live under `tests/property/` and are marked `property`.

The local `dev` profile prioritizes iteration speed. CI uses a deterministic higher-volume
profile through:

```bash
HYPOTHESIS_PROFILE=ci pytest -m property
```

Good candidates include:

- binary-block encode/decode invariants;
- truncated and over-limit protocol data;
- text framing and terminator rules;
- numeric, boolean, CSV, and engineering-value parsing;
- valid/invalid `ReadRequest` combinations;
- retry/backoff schedule invariants;
- concrete-driver range/choice validators and value formatting.

Hypothesis should complement explicit regression cases, not replace them.

## PyVISA-sim policy

VISA integration tests are marked `visa_sim`. The reference test exercises the real path:

```text
ScpiSession
  -> ScpiClient
    -> VisaTransport
      -> PyVISA
        -> PyVISA-sim
```

A concrete VISA driver should add a device-specific simulator definition where technically
feasible and cover at least:

- connection and identity;
- one representative write/set operation;
- one representative query/read operation;
- typed parsing through the public driver API;
- reconnect/session behavior when relevant.

Behavior PyVISA-sim cannot represent cleanly belongs in scripted simulation or HIL tests.

## Scripted simulation policy

`ScriptedScpiTransport` is the preferred deterministic command-level simulator for scenarios
such as:

- exact command verification;
- SCPI error queues;
- malformed responses;
- read timeouts;
- disconnect/fault recovery;
- retry behavior;
- binary block fixtures;
- unusual vendor responses.

Device-specific command trees and fixtures belong in the concrete driver's repository, not in
`scpi-driver-core`.

## Hardware/HIL policy

Normal CI must not require physical hardware. HIL tests should be explicitly marked:

```python
@pytest.mark.hardware
```

HIL is expected for claims that simulators cannot establish, including vendor quirks,
real timing, binary transfer compatibility, protection-state behavior, calibration, and
physical output transitions.

A dedicated hardware runner may execute those tests separately, but the default pull-request
suite should continue to use:

```bash
pytest -m "not hardware"
```

## CI quality gate

The repository runs the following equivalent checks across Python 3.10, 3.11, 3.12, and 3.13:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not hardware" --cov=scpi_driver_core --cov-report=term-missing
python -m build
```

The configured coverage threshold is 90%. The package build is performed on the newest
matrix version while all supported versions execute the test harness.

## Downstream concrete-driver baseline

For an AI-generated, migrated, or manually written concrete driver, the final harness should
normally contain:

1. deterministic unit tests for device semantics and validation;
2. scripted/mock tests for exact protocol and failure handling;
3. Hypothesis tests where an input space has useful invariants or boundaries;
4. PyVISA-sim integration when VISA is supported and the behavior is representable;
5. pytest-timeout protection for the complete automated suite;
6. clearly separated HIL tests for behavior requiring real equipment.

The test suite should exercise the public driver API and reuse `scpi-driver-core` transport,
session, retry, parsing, and error semantics instead of reimplementing them in test-only code.
If a layer is not applicable, document why.

## Commands

```bash
pytest -m "not hardware"                         # complete hardware-free harness
pytest -m property                               # Hypothesis properties
pytest -m visa_sim                               # PyVISA-sim integration
pytest -m watchdog                               # deadlock/hang regressions
HYPOTHESIS_PROFILE=ci pytest -m property         # CI-volume properties
pytest -m "not hardware" --cov=scpi_driver_core  # coverage gate
```

See `tests/README.md` for repository layout and `AGENTS.md` for AI/code-agent completion
requirements.
