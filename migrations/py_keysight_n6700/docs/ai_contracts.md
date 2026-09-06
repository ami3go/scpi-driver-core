# AI Driver and Test-Bench Contracts

Release v26.09 implements the project source specifications:

- **RFDS-017 v3.0**: `ai/keysight_n6700_ai_contract.yaml` and `ai/keysight_n6700_ai_contract.lock`
- **RFDS-018 v1.0**: `system_ai_contract.yaml`

## Driver contract

`ai/keysight_n6700_ai_contract.yaml` describes the Keysight N6700 library without requiring an AI agent to inspect Python source. It includes:

- identity and mental model;
- session/channel state machine;
- consumed and provided resources;
- runtime and external dependencies;
- one capability record for every public Robot Framework keyword;
- exact signatures, inputs, outputs, preconditions, postconditions, side effects, risk, timing, stabilization, retry, errors, and resource ownership;
- error catalogue and safety rules;
- verification objectives and pass/fail oracles;
- setup, teardown, failure cleanup, limitations, planning hints, fail-closed UNKNOWN handling, and conformance rules.

The lock file hashes both contracts, the Robot library source, the generator, and the ordered public keyword list. CI rejects stale contracts.

## Bench contract

`system_ai_contract.yaml` is a safe standalone bench template. It registers this driver and describes resource conflicts, signal flow, measurement preferences, reusable test templates, scheduling rules, and emergency shutdown behavior.

It is **not** a completed physical bench description. All site-dependent fields remain `UNKNOWN`, and energization is blocked until the bench owner supplies and approves:

- actual VISA or Ethernet resource;
- installed module model per channel;
- channel-to-DUT/fixture wiring and polarity;
- cable, connector, fixture, and DUT limits;
- safety-zone limits and interlock/emergency-stop details;
- stabilization and measurement-source requirements.

## Deterministic generation

```bash
python scripts/generate_ai_contract.py
python scripts/generate_ai_contract.py --check
```

The contract files use JSON-compatible YAML 1.2 for deterministic generation and standard-library validation.
