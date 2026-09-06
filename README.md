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
- a scripted instrument simulator for testing drivers without hardware

Not yet implemented: the representative driver migrations that validate the
architecture against real instruments (Phase 15).

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

### Slow commands

Some instruments take minutes over a single command — a sweep, a long
integration, a calibration, ranging on a supply or a load. Waiting for one by
simply reading with a long timeout is the trap: if the estimate is short by a
second the read times out, and a timed-out read cannot be retried, because the
reply is still in flight and would be returned as the answer to whatever is
asked next. A correct transport therefore faults, and the session is over.

Poll instead. `*OPC` returns immediately and sets a bit when the pending work
finishes; `*ESR?` answers immediately even while the instrument is busy. Every
read stays short, and a wait that runs over its deadline raises without having
damaged anything:

```python
from scpi_driver_core.scpi import Ieee4882

ieee = Ieee4882(client)
result = ieee.run_until_complete("CALibration:ALL", timeout_s=900.0)
print(result.polls, result.elapsed_s, hex(result.event_status))
```

The poll interval starts short and backs off, so a command that finishes
quickly is noticed at once and a long one is not polled thousands of times.
`OperationTimeoutError` on the deadline leaves the connection open and usable,
so the caller can read the error queue or abort. `wait_for_completion()` is the
same wait without sending a command, for work already in progress.

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
