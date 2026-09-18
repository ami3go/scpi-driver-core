# Examples

Every example except `05_real_instruments.py` runs as-is without hardware or an external
network endpoint by scripting a simulated instrument. The automated test suite executes these
examples so they cannot silently rot.

```bash
python examples/01_typed_queries.py
```

| Example | Shows |
| --- | --- |
| `01_typed_queries.py` | `write`/`query` and typed helpers, including tolerant unit-suffixed numbers |
| `02_sessions_and_health.py` | named sessions, identity validation, registry use, and why "open" is not "answering" |
| `03_binary_block_transfer.py` | IEEE-488.2 block transfer in both directions while preserving every byte |
| `04_tracing_and_audit.py` | protocol tracing to JSONL with redaction of a calibration secret |
| `05_real_instruments.py` | the same core over VISA, TCP, UDP, and serial; illustrative and requires hardware |

The point of `05_real_instruments.py` is that only transport construction differs. Session,
SCPI, parsing, retry, and tracing infrastructure above it remains transport-independent.

## Examples versus test simulators

The examples use deterministic scripted behavior to demonstrate API usage. They are not a
substitute for the complete test harness. Repository validation additionally includes
Hypothesis properties, PyVISA-sim integration, transport conformance, local socket tests, and
pytest-timeout concurrency watchdogs.

See `docs/testing.md` and `tests/README.md` for the test architecture. Concrete drivers should
reuse those patterns and keep real-instrument/HIL tests separate from normal hardware-free CI.
