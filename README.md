# scpi-driver-core

Framework-independent shared infrastructure for Python SCPI/IEEE-488.2 instrument drivers.

The same concrete driver built on this package can be used unchanged from Robot Framework,
HardPy/pytest, plain Python, Jupyter, or a CLI. Nothing under `src/scpi_driver_core/`
imports `robot`, `hardpy`, or `pytest`.

Current development version: **0.1.0.dev5**.

## Status

The generic core is implemented and exercised by a hardware-free CI harness. The remaining
release blocker for `v0.1.0` is representative migration proof against real concrete drivers
and instruments. The architecture and acceptance criteria are defined in
`task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`; current test-harness requirements are also
summarized in `docs/testing.md` and `AGENTS.md`.

Available now:

- common typed error hierarchy (`ScpiDriverError` and subclasses)
- byte-oriented `Transport` protocol and explicit transport state model
- VISA, serial, TCP, UDP, mock, and scripted transports
- reusable transport conformance tests
- `ScpiTextCodec`, generic parsers, CSV helpers, and engineering-value parsing
- `ScpiClient` text, byte, typed-query, binary-block, retry, and error-checking operations
- IEEE-488.2 common-command helpers (`Ieee4882`)
- SCPI error-queue draining with opt-in automatic checking
- bounded polling, safe retry/replay policy, and confirmation guards
- named sessions, connection health, reconnect generations, and a session registry
- protocol tracing, JSONL audit, and redaction hooks
- scripted instrument simulation for deterministic driver tests
- a layered hardware-free test harness using Hypothesis, PyVISA-sim, and pytest-timeout

Not yet complete: representative driver migrations and HIL evidence required by the release
acceptance criteria.

## Quick example

```python
from scpi_driver_core import ScpiClient
from scpi_driver_core.transport import MockTransport

transport = MockTransport()
transport.open()
transport.feed(b"3.14159\n")

client = ScpiClient(transport)
value = client.query_float("MEAS?")
assert value == 3.14159
```

## Installation

```bash
pip install scpi-driver-core          # TCP and UDP only, no third-party runtime deps
pip install scpi-driver-core[visa]    # adds PyVISA
pip install scpi-driver-core[serial]  # adds pyserial
pip install scpi-driver-core[all]
```

Requires Python 3.10 or newer.

For development and the complete test harness:

```bash
python -m pip install -e ".[dev,all]"
```

## Test harness

Normal CI is intentionally independent of physical laboratory hardware and external network
endpoints. It combines complementary test layers rather than relying on one simulator:

| Layer | Tool | Purpose |
| --- | --- | --- |
| Unit tests | pytest | Exact behavior, error paths, lifecycle, parsers, tracing |
| Transport contract | pytest | Common lifecycle, bounds, fault and serialization rules for every backend |
| Property tests | Hypothesis | Generated protocol, parser, framing, bounds and retry cases |
| VISA integration | PyVISA-sim | Real `VisaTransport -> PyVISA -> simulator` integration path |
| Socket integration | local TCP/UDP endpoints | Real local socket behavior without external infrastructure |
| Concurrency watchdog | pytest-timeout | Deadlocks and unbounded hangs fail in finite time |
| Hardware/HIL | `hardware` marker | Real instrument quirks and physical behavior; excluded from normal CI |

Run the same hardware-free gate used by CI:

```bash
pytest -m "not hardware" --cov=scpi_driver_core --cov-report=term-missing
```

Focused runs:

```bash
pytest -m property
pytest -m visa_sim
pytest -m watchdog
HYPOTHESIS_PROFILE=ci pytest -m property
```

The configured coverage gate is 90%. The normal matrix validates Python 3.10, 3.11, 3.12,
and 3.13.

See `docs/testing.md` and `tests/README.md` for the harness design and downstream-driver
expectations.

## Design principles

- The canonical transport boundary is **bytes**, not `str`, so waveform, arbitrary-waveform,
  setup, and file transfers use the same contract as text commands.
- Reads are explicitly bounded; `ReadRequest` rejects combinations that would permit an
  unbounded read or silently ignore fields.
- Manufacturer- and model-specific behavior stays in concrete driver packages. The core
  provides mechanisms, not instrument semantics.
- Retries are explicit and limited to operations the caller has classified as safe to replay.
- Simple, explicit driver methods are preferred over speculative abstraction. Generic layers
  should be extracted only after reuse is demonstrated by multiple real drivers.

## Documentation

- `docs/README.md` — architecture and design decisions
- `docs/testing.md` — test-harness architecture and downstream-driver requirements
- `docs/acceptance.md` — current acceptance status and release blockers
- `tests/README.md` — test-suite layout and commands
- `examples/README.md` — runnable examples
- `AGENTS.md` — requirements for AI/code agents generating or migrating drivers
- `CONTRIBUTING.md` — development workflow and quality gates
- `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md` — original detailed implementation specification

See `CONTRIBUTING.md` before opening a pull request.
