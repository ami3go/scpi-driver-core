# Package compliance review — v26.05

## Result

The release uses `rf_keysight_n6700_v26.05.zip` with fixed internal root `rf_keysight_n6700/` and retains all mandatory project folders and earlier release records.

## RFDS-019 regression controls

- Runtime booleans are normalized before guard evaluation.
- Unsafe `Skip If    not ${HIL_ENABLE|ALLOW_RESET|ALLOW_ACTIVE_OUTPUT}` patterns are prohibited by the static validator.
- Windows simulator mode is explicitly non-HIL.
- The self-check remains non-energizing unless active-output authorization is explicitly true.

## Release status

**Corrected hardware-validation candidate.** Static/package gates pass; physical N6775A execution remains required.
