# Examples

Every example except `05_real_instruments.py` runs as-is, with no hardware and no
network, by scripting a simulated instrument. The test suite runs them, so they
cannot rot.

```bash
python examples/01_typed_queries.py
```

| Example | Shows |
| --- | --- |
| `01_typed_queries.py` | `write`/`query` and the typed helpers, including tolerant unit-suffixed numbers |
| `02_sessions_and_health.py` | named sessions, identity validation, the registry, and why "open" is not "answering" |
| `03_binary_block_transfer.py` | IEEE-488.2 block transfer in both directions, preserving every byte |
| `04_tracing_and_audit.py` | protocol tracing to JSONL with redaction of a calibration secret |
| `05_real_instruments.py` | the same code over VISA, TCP, UDP, and serial — illustrative, needs an instrument |

The point of `05` is that only the transport construction differs. Everything
above it is identical whichever way the instrument is attached.
