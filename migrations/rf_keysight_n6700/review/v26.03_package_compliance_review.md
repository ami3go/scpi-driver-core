# Package Compliance Review — v26.03

| Project requirement | Result | Evidence |
|---|---|---|
| ZIP uses `rf_{driver_name}_v{year}.{release}` | PASS | `rf_keysight_n6700_v26.03.zip` |
| ZIP contains one fixed internal root | PASS | `rf_keysight_n6700/` |
| History folder describes each release | PASS | v26.01, v26.02, and v26.03 records retained |
| Review folder contains code/package reviews | PASS | v26.01, v26.02, and v26.03 reviews retained |
| At least 10 examples | PASS | 14 Robot Framework and 17 executable Python examples |
| Scripts run examples | PASS | BAT, PowerShell, and POSIX launchers |
| GitHub README current | PASS | Root README identifies v26.03 and AI contracts |
| GitHub Pages current | PASS | AI-contract page, release pages, strict MkDocs build, Pages workflow |
| PyCharm and Robot Framework setup guide | PASS | `guide/pycharm_robot_framework_setup.md` |
| RFDS-017 required files | PASS | `ai/ai_contract.yaml`, `ai/ai_contract.lock` |
| RFDS-017 mandatory sections | PASS | Verified by package verifier |
| One capability per Robot keyword | PASS | Exact ordered coverage of 62 decorated keywords |
| RFDS-017 capability fields | PASS | Signature, purpose, I/O, pre/postconditions, side effects, risk, timing, stabilization, retry, errors, resources |
| RFDS-018 required file | PASS | `system_ai_contract.yaml` |
| RFDS-018 mandatory sections | PASS | Verified by package verifier |
| Unknown bench data fails closed | PASS | Site configuration required; energization blocked |
| AI contract drift detection | PASS | Deterministic generator, lock hashes, CI `--check` |
| Source standards retained | PASS | RFDS-017 v3.0 and RFDS-018 v1.0 under `standards/` |
| Current wheel and source distribution | PASS | `dist/` artifacts for 26.3.0 |

## Conclusion

v26.03 conforms to the Robot Framework Driver package requirements and implements the supplied RFDS-017/RFDS-018 source specifications. The AI bench contract remains intentionally non-executable for energizing workflows until site-specific physical data is completed and approved.
