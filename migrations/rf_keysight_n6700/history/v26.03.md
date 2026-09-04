# Release History — v26.03

**Date:** 2026-07-21  
**Archive:** `rf_keysight_n6700_v26.03.zip`  
**Fixed internal root:** `rf_keysight_n6700/`  
**Python package version:** `26.3.0`

## Purpose

This release updates the driver against the project source specifications RFDS-017 AI Driver Contract v3.0 and RFDS-018 AI Test Bench Contract v1.0. The goal is to let an AI test-planning agent understand and safely compose the driver without reading Python source code.

## Changes

1. Added `ai/ai_contract.yaml`, implementing every mandatory RFDS-017 section.
2. Added exactly one capability record for each of the 62 public Robot Framework keywords.
3. Added exact keyword signatures, typed inputs/outputs, preconditions, postconditions, side effects, risk, timing, stabilization, retry policy, errors, resource ownership, safe defaults, and module requirements.
4. Added a driver mental model, channel/session state machine, error catalogue, safety rules, verification objectives with pass/fail oracles, setup/teardown contract, limitations, planning hints, UNKNOWN handling, and conformance rules.
5. Added `ai/ai_contract.lock` with the ordered keyword list and SHA-256 hashes of both AI contracts, the Robot library source, and the deterministic generator.
6. Added `system_ai_contract.yaml`, implementing all RFDS-018 bench sections.
7. Made the bench contract fail closed until site-specific transport, module map, topology, polarity, DUT limits, interlock, safety zones, and stabilization requirements are configured.
8. Added reusable read-only discovery, safe source-channel, and emergency-shutdown test templates.
9. Added `scripts/generate_ai_contract.py` with deterministic generation and `--check` drift detection.
10. Extended the package verifier to validate mandatory RFDS sections, exact keyword coverage, mandatory capability fields, lock hashes, current driver version, and fail-closed bench behavior.
11. Added CI, test, build, and cross-platform verification enforcement for AI-contract freshness.
12. Added project-source copies of RFDS-017 v3.0 and RFDS-018 v1.0 under `standards/`.
13. Added AI-contract documentation to README and GitHub Pages.
14. Updated version metadata, release records, distributions, Libdoc, Pages, manifest, checksums, and final archive for v26.03.

## Functional impact

No intentional SCPI command, transport, module-support, output-default, or public Robot keyword behavior changed. The release adds machine-verifiable semantics and stricter release gates around the existing implementation.

## Compatibility

- Fixed unpacked folder remains `rf_keysight_n6700/`.
- Existing Robot Framework suites remain compatible.
- Python package version advances from `26.2.0` to `26.3.0`.
- AI planners should use `ai/ai_contract.yaml` and merge it into a completed site-specific RFDS-018 bench contract before generating energizing tests.
