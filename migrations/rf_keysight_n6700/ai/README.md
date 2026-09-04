# AI Contracts

This directory contains the RFDS-017 contract for the Keysight N6700 Robot Framework driver.

- `keysight_n6700_ai_contract.yaml` — complete AI-readable driver semantics, including one capability entry for every Robot keyword.
- `keysight_n6700_ai_contract.lock` — deterministic lock containing the exact keyword list and SHA-256 hashes of the contracts, generator, and authoritative library source.

The repository root also contains `system_ai_contract.yaml`, an RFDS-018 bench-level contract template. It deliberately fails closed: site-specific resource addresses, module map, physical wiring, polarity, DUT limits, safety-zone limits, interlock details, and stabilization requirements remain `UNKNOWN` until configured by the bench owner.

## Regeneration

Run after any public keyword, signature, documentation, safety rule, package version, or bench-template change:

```bash
python scripts/generate_ai_contract.py
```

Check that committed contracts are current:

```bash
python scripts/generate_ai_contract.py --check
```

The files use deterministic JSON-compatible YAML 1.2, so standard YAML parsers and JSON parsers can read them.
