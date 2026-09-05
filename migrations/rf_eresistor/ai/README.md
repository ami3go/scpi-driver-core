# AI contract

`eresistor_ai_contract.yaml` is the canonical RFDS-017 v3.0 machine-readable contract for this driver. It is JSON-formatted YAML 1.2 so both JSON-only and YAML-aware agents can parse it without ambiguity.

Before using the contract, verify its SHA-256 and capability count against `eresistor_ai_contract.lock`. Regenerate both files after any public Robot keyword or semantic change:

```bash
python tools/generate_ai_contract.py
python -m pytest tests/test_ai_contract.py
```

The contract describes one driver only. Bench topology, relay/DMM routing, shared resources, tolerances, and cross-driver sequencing belong in RFDS-018. Those values remain `UNKNOWN` until a populated bench contract is supplied.
