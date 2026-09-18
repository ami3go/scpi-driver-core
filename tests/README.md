# Tests

The test suite is added phase-by-phase with the implementation task. Default CI never
requires physical hardware or an external network endpoint.

## Harness layers

The harness deliberately uses several complementary layers rather than treating one
simulator as proof of correctness:

| Layer | Tool / location | What it proves |
| --- | --- | --- |
| Deterministic unit tests | `pytest`, `tests/unit/` | Exact behavior, error paths, state transitions, parsers, retries, tracing |
| Transport conformance | `pytest`, `tests/transport_contract/` | Every transport obeys the same lifecycle, bounds, serialization and fault rules |
| Property tests | `Hypothesis`, `tests/property/` | Generated boundary/protocol cases that are impractical to enumerate manually |
| VISA integration | `PyVISA-sim`, `tests/integration/test_pyvisa_sim.py` | The real `VisaTransport -> PyVISA -> simulator` path works end-to-end |
| Local socket integration | `tests/integration/test_tcp_transport.py`, `test_udp_transport.py` | TCP/UDP behavior against real local sockets without external infrastructure |
| Concurrency watchdog | `pytest-timeout`, `tests/integration/test_timeout_watchdog.py` | Lock-order/deadlock regressions fail in bounded time instead of hanging CI |
| Hardware/HIL | `hardware` marker | Real instrument quirks and behavior; intentionally excluded from default CI |

`pytest-timeout` also supplies global bounds of 30 seconds per test and 600 seconds for
the complete suite. Individual deadlock/watchdog tests may use a shorter explicit bound.
Hypothesis uses the `dev` profile locally and a deterministic higher-volume `ci` profile
when `HYPOTHESIS_PROFILE=ci` is set.

## Adding a transport backend

Subclass `TransportContract` from `transport_contract/contract.py` and implement its
hooks; the whole conformance suite then runs against the new backend:

```python
class TestTcpTransportContract(TransportContract):
    supports_failure_injection = True

    def create_transport(self) -> Transport:
        return TcpTransport(host="127.0.0.1", port=self.port)

    def prime(self, transport: Transport, data: bytes) -> None:
        self.server.send(data)
```

Set the `supports_*` capability flags to declare what the backend fake can simulate
and whether it has stream or message semantics; tests needing an unsupported
capability skip themselves. Backend behavior the contract cannot express belongs in
`unit/` or `integration/`.

## Running

```bash
pytest -m "not hardware"                         # complete hardware-free harness
pytest -m property                               # Hypothesis only
pytest -m visa_sim                               # PyVISA-sim integration only
pytest -m watchdog                               # concurrency/hang regression tests
HYPOTHESIS_PROFILE=ci pytest -m property         # deterministic CI-volume properties
pytest -m "not hardware" --cov=scpi_driver_core  # full harness with coverage
```

The coverage run fails below the repository's configured 90% threshold.
