# Tests

The test suite is added phase-by-phase with the implementation task. Default CI never
requires physical hardware or an external network endpoint.

## Groups

- `unit/` — value types, exceptions, codec, parsers. Populated.
- `transport_contract/` — one reusable suite run against every transport backend, so
  each new backend inherits the same state-machine and bounds guarantees. Empty until
  the `Transport` protocol and `MockTransport` land.
- `integration/` — local simulated endpoints (loopback sockets, scripted transports).
  Empty; marked with the `integration` marker when added.

## Running

```bash
pytest                          # whole suite
pytest --cov=scpi_driver_core   # with coverage; fails under 90%
pytest -m "not hardware"        # skip anything needing an instrument
```
