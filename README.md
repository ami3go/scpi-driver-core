# scpi-driver-core

Framework-independent shared infrastructure for Python SCPI/IEEE-488.2 instrument drivers.

The same concrete driver built on this package is usable unchanged from Robot Framework,
HardPy/pytest, plain Python, Jupyter, or a CLI. Nothing under `src/scpi_driver_core/`
imports `robot`, `hardpy`, or `pytest`.

## Status

Early development, working toward `v0.1.0`. The architecture and acceptance criteria are
specified in `task/SCPI_DRIVER_CORE_IMPLEMENTATION_TASK.md`, which is being implemented in
phases.

Available now:

- the common error hierarchy (`ScpiDriverError` and its subclasses)
- transport value types: `TransportState`, `TransportDescriptor`, `ReadMode`,
  `ReadRequest`, `WriteResult`, `FlushDirection`, `ReplayPolicy`

Not yet implemented: the transports themselves, the SCPI client and codec, IEEE-488.2
helpers, binary blocks, sessions, tracing, and simulation.

## Installation

```bash
pip install scpi-driver-core          # TCP and UDP only, no third-party runtime deps
pip install scpi-driver-core[visa]    # adds PyVISA
pip install scpi-driver-core[serial]  # adds pyserial
pip install scpi-driver-core[all]
```

Requires Python 3.10 or newer.

## Design

- The canonical transport boundary is **bytes**, not `str`, so waveform, arbitrary-waveform,
  and setup/file transfers work through the same contract as text commands. Text framing
  lives above that boundary.
- Reads are explicitly bounded; `ReadRequest` rejects any combination of fields that would
  permit an unbounded read, or that sets a field the selected `ReadMode` does not use.
- Manufacturer- and model-specific behavior stays in concrete driver packages. The core
  provides primitives, not instrument semantics.

See `CONTRIBUTING.md` for development setup and the quality gates.
