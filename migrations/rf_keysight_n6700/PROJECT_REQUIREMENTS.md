# Robot Framework Driver Project Requirements

This repository follows the common Robot Framework Driver package standard and the supplied AI contract standards RFDS-017 v3.0 and RFDS-018 v1.0.

## Mandatory release format

| Requirement | Keysight N6700 implementation |
|---|---|
| ZIP name | `rf_keysight_n6700_v26.09.zip` |
| Fixed internal root | `rf_keysight_n6700/` |
| Python distribution version | `26.9.0` |
| Root package layout | `keysight_n6700/` and `KeysightN6700Library/`; no `src/` |
| Change history | `history/v26.09.md` plus retained earlier records |
| Release review | `review/v26.09_code_review.md` and package compliance review |
| Examples | 14 Robot Framework and 17 executable Python examples |
| Example launchers | BAT, PowerShell, and POSIX shell scripts in `scripts/` |
| GitHub README | Root `README.md` |
| GitHub Pages | `docs/`, `mkdocs.yml`, and `.github/workflows/pages.yml` |
| IDE guide | `guide/pycharm_robot_framework_setup.md` |

## RFDS-017 AI Driver Contract

| Requirement | Implementation |
|---|---|
| Required files | `ai/keysight_n6700_ai_contract.yaml`, `ai/keysight_n6700_ai_contract.lock` |
| Identity and mental model | Top-level contract sections |
| State machine | Session/channel states and transitions |
| Resources and dependencies | Consumed/provided resources and runtime/external dependencies |
| One capability per Robot keyword | 62 generated capability records, exact ordered source match |
| Capability semantics | Signature, purpose, inputs/outputs, pre/postconditions, side effects, risk, timing, stabilization, retry, errors, resources |
| Error catalogue and safety | Explicit categorized error/planner actions and fail-closed safety rules |
| Verification objectives | Pass/fail oracles for identity, module map, safe start, setpoints, outputs, measurements, protection, shutdown |
| Setup/teardown | Normal and failure cleanup sequence |
| Limitations/planning/UNKNOWN | Explicit limitations, planning hints, fail-closed UNKNOWN handling |
| Conformance | Deterministic generator, lock hashes, verifier, tests, and CI |

## RFDS-018 AI Test Bench Contract

`system_ai_contract.yaml` contains all required bench sections: available drivers, topology, shared resources, signal graph, preferred measurement sources, requirement coverage, reusable test templates, constraints, scheduling rules, and global safety.

The bundled file is a safe template, not a completed laboratory authorization. It uses `REQUIRES_SITE_CONFIGURATION` and blocks energization until resource address, module map, physical wiring, polarity, DUT/fixture limits, safety zones, external interlock, and stabilization requirements are supplied and approved.

## Automated enforcement

Generate and lock the contracts:

```bash
python scripts/generate_ai_contract.py
```

Check contract freshness and package structure:

```bash
python scripts/generate_ai_contract.py --check
python scripts/verify_project_package.py --source . --expected-release 26.07
```

After building the release archive:

```bash
python scripts/verify_project_package.py \
  --archive ../rf_keysight_n6700_v26.09.zip \
  --expected-release 26.07 \
  --require-artifacts
```

The verifier checks archive naming, fixed root, required project content, example count, current release records, Python/release version consistency, RFDS mandatory sections, exact keyword coverage, capability fields, contract-lock hashes, fail-closed bench UNKNOWN handling, generated artifacts, and absence of a `src/` layout.
