# Release history — v26.04

- **Version:** 26.04
- **Python package:** 26.4.0
- **Archive:** `rf_keysight_n6700_v26.04.zip`
- **Date:** 2026-07-24
- **Phase/gate:** RFDS-019 connected self-check implementation and release gate

## User-visible changes

- Added a complete Robot Framework self-check for an N6775A module.
- Added BAT, PowerShell, and shell runners with timestamped evidence directories.
- Added a guide describing safe VISA and Ethernet execution.

## Internal architecture changes

- Added transport-boundary JSONL protocol audit records to `N6700.write_scpi` and `N6700.query_scpi`.
- Added deterministic inventory/vector/exclusion validation and result post-processing.

## Public Robot API

No public keyword was added, removed, renamed, deprecated, or behaviorally changed. The self-check inventories all 62 existing keywords. N6775A-inapplicable SMU/load keywords are called and must raise the documented unsupported-feature failure before transmission.

## Safety changes

- Physical runs require explicit HIL enablement through the runner.
- Reset and output-enable tests are separate, disabled-by-default gates.
- Setup, per-test teardown, and suite teardown force the selected output OFF.
- Requested test values are checked against 60 V, 5 A, and 300 W profile limits.
- Final state intentionally leaves all controllable outputs/inputs OFF.

## Tests and evidence

- 21 Robot test cases.
- 62/62 public keywords inventoried.
- 44 protocol/callability vectors.
- 18 explicit profile exclusions.
- Invalid-command, invalid-argument, unsupported-feature, and reconnect recovery paths.
- Machine-readable keyword coverage, vector results, traces, environment, identity, exclusions, and Markdown summary.

## Compatibility impact

Backward compatible with v26.03 public API. Protocol tracing adds file I/O only when `audit_log_path` is supplied.

## Known limitations

- Physical N6775A execution was not possible in the package build environment.
- Electrical accuracy/calibration is outside RFDS-019 and requires independent metrology.
- Reset and energizing vectors remain unexecuted until explicitly authorized at the real bench.

## Hardware-validation status

**HIL PENDING.** Static conformance and core simulator tests pass; final hardware acceptance requires the user's N6700 mainframe and N6775A module.
