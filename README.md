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
- the `Transport` protocol, and `MockTransport` as its reference implementation
- a reusable transport conformance suite every backend must pass
- `ScpiTextCodec`, generic response parsers, and engineering-value parsing
- `ScpiClient` text, byte, and typed-query operations with correlated operation IDs
- standard-library TCP and UDP transports with finite timeouts and explicit
  stream/datagram semantics
- optional pyserial transport with configurable line settings, DTR/RTS, and
  directional buffer flushing
- optional PyVISA transport covering GPIB, USBTMC, TCPIP INSTR/SOCKET and ASRL

- IEEE-488.2 common-command helpers (`Ieee4882`)
- IEEE-488.2 definite-length binary blocks, for waveform and setup transfers
- SCPI error-queue draining with opt-in automatic checking
- bounded polling, explicit retry/replay policy, and confirmation guards
- named sessions, connection health, and a session registry
- protocol tracing, JSONL audit, and redaction hooks

Not yet implemented: the scripted device-simulation transport (Phase 14), and the
representative driver migrations that validate the architecture (Phase 15).

```python
from scpi_driver_core.transport import MockTransport, ReadMode, ReadRequest

transport = MockTransport()
transport.open()
transport.feed(b"KEYSIGHT,N6700C,MY56000102,D.01.09\n")

reply = transport.transact(
    b"*IDN?\n",
    ReadRequest(mode=ReadMode.UNTIL_TERMINATOR, terminator=b"\n"),
)
assert reply == b"KEYSIGHT,N6700C,MY56000102,D.01.09"
```

The same transport can be used through the text client:

```python
from scpi_driver_core import ScpiClient

transport.feed(b"3.14159\n")
client = ScpiClient(transport)
value = client.query_float("MEAS?")
```

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
