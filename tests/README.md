# Tests

The default suite is a hardware-free reference harness for both `scpi-driver-core` itself and
for concrete driver repositories that adopt the core. Normal CI never requires physical
hardware or an external network endpoint.

The maintained test architecture is also described in `docs/testing.md`. The original
implementation task is supplemented by `task/TEST_HARNESS_ADDENDUM.md`.

## Harness layers

The harness deliberately uses complementary layers rather than treating one simulator as
proof of correctness:

| Layer | Tool / location | What it proves |
| --- | --- | --- |
| Deterministic unit tests | `pytest`, `tests/unit/` | Exact behavior, error paths, state transitions, parsers, retries, tracing |
| Transport conformance | `pytest`, `tests/transport_contract/` | Every applicable transport obeys common lifecycle, bounds, serialization and fault rules |
| Property tests | `Hypothesis`, `tests/property/` | Generated boundary/protocol cases that are impractical to enumerate manually |
| Scripted simulation | `ScriptedScpiTransport` tests | Exact SCPI traffic, malformed replies, error queues, timeouts, disconnect/recovery paths |
| VISA integration | `PyVISA-sim`, `tests/integration/test_pyvisa_sim.py` | Real `VisaTransport -> PyVISA -> simulator` integration works end-to-end |
| Local socket integration | `test_tcp_transport.py`, `test_udp_transport.py` | TCP/UDP behavior against real local sockets without external infrastructure |
| Concurrency watchdog | `pytest-timeout`, `tests/integration/test_timeout_watchdog.py` | Lock-order/deadlock regressions fail in bounded time instead of hanging CI |
| Hardware/HIL | `hardware` marker | Real instrument quirks/behavior; intentionally excluded from default CI |

`pytest-timeout` supplies global bounds of 30 seconds per test and 600 seconds for the complete
suite. Individual deadlock/watchdog tests may use a shorter explicit bound.

Hypothesis uses the `dev` profile locally and a deterministic higher-volume `ci` profile when
`HYPOTHESIS_PROFILE=ci` is set.

## Adding a transport backend

Subclass `TransportContract` from `transport_contract/contract.py` and implement its hooks;
the common conformance suite then runs against the backend:

```python
class TestTcpTransportContract(TransportContract):
    supports_failure_injection = True

    def create_transport(self) -> Transport:
        return TcpTransport(host="127.0.0.1", port=self.port)

    def prime(self, transport: Transport, data: bytes) -> None:
        self.server.send(data)
```

Set the `supports_*` capability flags to declare what the backend fake can simulate and whether
it has stream or message semantics. Tests needing an unsupported capability skip themselves.
Backend behavior the contract cannot express belongs in `unit/` or `integration/`.

## Using the harness in a concrete driver

Do not copy core internals into a driver test suite. Reuse the patterns and test through the
concrete driver's public API.

A normal concrete-driver suite should combine:

```text
unit/device-semantic tests
ScriptedScpiTransport command/failure scenarios
Hypothesis boundary/property tests where useful
PyVISA-sim integration for representable VISA behavior
pytest-timeout finite run bounds
separate hardware/HIL tests
```

Device-specific simulator definitions and expected command/response fixtures belong in the
concrete driver repository. If a layer is not applicable, document why.

## Running

```bash
pytest -m "not hardware"                         # complete hardware-free harness
pytest -m property                               # Hypothesis only
pytest -m visa_sim                               # PyVISA-sim integration only
pytest -m watchdog                               # concurrency/hang regression tests
HYPOTHESIS_PROFILE=ci pytest -m property         # deterministic CI-volume properties
pytest -m "not hardware" --cov=scpi_driver_core  # full harness with coverage
```

The coverage run fails below the configured 90% threshold. CI runs the hardware-free harness
on Python 3.10, 3.11, 3.12, and 3.13.
