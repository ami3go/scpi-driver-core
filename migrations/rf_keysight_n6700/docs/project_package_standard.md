# Project Package Standard

The release archive is named `rf_keysight_n6700_v26.09.zip` and always contains exactly one top-level folder: `rf_keysight_n6700/`.

The repository includes release history, code reviews, more than ten examples, cross-platform example launchers, PyCharm and Robot Framework setup guidance, GitHub Pages content, CI, wheel/source distributions, and generated Libdoc.

## Verify the unpacked repository

```bash
python scripts/verify_project_package.py --source . --expected-release 26.07
```

## Verify the final ZIP

```bash
python scripts/verify_project_package.py \
  --archive ../rf_keysight_n6700_v26.09.zip \
  --expected-release 26.07 \
  --require-artifacts
```

A failed check exits non-zero and identifies the missing or inconsistent requirement.

## AI contract standards

The package also requires:

- `ai/keysight_n6700_ai_contract.yaml` and `ai/keysight_n6700_ai_contract.lock` for RFDS-017 v3.0;
- `system_ai_contract.yaml` for RFDS-018 v1.0;
- exact capability coverage of every public Robot keyword;
- deterministic lock hashes and CI drift checking;
- fail-closed handling of unknown bench topology and limits.
