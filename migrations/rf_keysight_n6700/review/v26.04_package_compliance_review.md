# Package compliance review — v26.04

## Result

The release preserves archive pattern `rf_keysight_n6700_v26.04.zip` and fixed internal root `rf_keysight_n6700/`.

## RFDS-019 artifacts

- `tests/conformance/driver_call_protocol_conformance.robot`
- `tests/conformance/resources/conformance_keywords.resource`
- `tests/conformance/resources/conformance_variables.resource`
- `tests/conformance/data/keyword_inventory.yaml`
- `tests/conformance/data/protocol_vectors.yaml`
- `tests/conformance/data/exclusions.yaml`
- `tests/conformance/expected/response_schemas/n6775a_responses.json`
- `scripts/run_n6775a_self_check.bat`
- `scripts/run_n6775a_self_check.ps1`
- `scripts/run_n6775a_self_check.sh`
- `scripts/validate_call_protocol_conformance.py`
- `scripts/summarize_n6775a_self_check.py`
- `docs/n6775a_self_check.md`

## Coverage

- Public keywords: 62/62 inventoried.
- Protocol/callability vectors: 44.
- Explicit exclusions: 18.
- Every public keyword has exactly one vector or exclusion.

## Release status

**Controlled hardware-validation candidate.** Package structure and static RFDS-019 consistency are complete. Real-device result evidence must be generated on an N6700 mainframe containing an N6775A.
