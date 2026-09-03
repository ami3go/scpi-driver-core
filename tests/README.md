# Tests

The test suite is added phase-by-phase with the implementation task. Default CI never
requires physical hardware or an external network endpoint.

## Groups

- `unit/` — value types, exceptions, backend-specific behavior, codec, parsers,
  and `ScpiClient` execution behavior.
- `transport_contract/` — one reusable suite run against every transport backend, so
  each new backend inherits the same state-machine and bounds guarantees.
- `integration/` — local loopback TCP and UDP endpoints. These tests require no
  physical hardware or external network access.

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
pytest                          # whole suite
pytest --cov=scpi_driver_core   # with coverage; fails under 90%
pytest -m "not hardware"        # skip anything needing an instrument
```
