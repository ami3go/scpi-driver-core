# Contributing

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev,all]"
```

The development extra installs pytest, pytest-cov, pytest-timeout, Hypothesis,
PyVISA-sim, mypy, Ruff, and build tooling. These remain development/test
dependencies and must not leak into the runtime package.

## Quality checks

Run the same hardware-free gate as CI before opening a pull request:

```bash
ruff check .
ruff format --check .
mypy src
pytest -m "not hardware" --cov=scpi_driver_core --cov-report=term-missing
python -m build
```

Useful focused runs:

```bash
pytest -m property
pytest -m visa_sim
pytest -m watchdog
HYPOTHESIS_PROFILE=ci pytest -m property
```

The coverage threshold is configured at 90%. Normal CI runs on Python 3.10,
3.11, 3.12, and 3.13 and must not require physical hardware or an external
laboratory endpoint.

## Test requirements

Choose the test layer that matches the failure surface:

- deterministic pytest tests for exact behavior and regressions;
- transport-contract tests for shared backend semantics;
- Hypothesis for protocol/parser/boundary invariants;
- `ScriptedScpiTransport` for exact SCPI traffic, malformed replies, error
  queues, timeouts, disconnects, and recovery;
- PyVISA-sim for real VISA-stack integration without hardware;
- pytest-timeout for finite suite/test bounds and explicit concurrency watchdogs;
- `hardware`-marked HIL tests for claims that require a real instrument.

Do not use blanket reruns to hide hangs or flaky behavior. Fix deterministic
failures and keep finite timeout guards.

See `docs/testing.md` and `tests/README.md` for the complete harness design.

## Design rules

- Keep runtime code independent of Robot Framework, HardPy, pytest, Hypothesis,
  pytest-timeout, and PyVISA-sim.
- Keep the canonical transport boundary byte-oriented.
- Keep manufacturer- and model-specific semantics in concrete driver packages.
- Do not add automatic retries for potentially non-idempotent writes.
- Add tests with every behavior change.
- Prefer composition and explicit methods over deep inheritance or speculative
  abstraction.
- Extract generic behavior only after reuse is demonstrated by multiple real
  drivers.
- Keep physical/HIL evidence separate from the default hardware-free CI gate.

See `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md` for the detailed architecture
and `AGENTS.md` for requirements that apply to AI/code-agent generated drivers.
