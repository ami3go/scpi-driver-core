# Release history — v26.05

- **Version:** 26.05
- **Python package:** 26.5.0
- **Archive:** `rf_keysight_n6700_v26.05.zip`
- **Date:** 2026-07-24
- **Phase/gate:** N6775A RFDS-019 execution hotfix and regression-prevention gate

## Corrected defects

1. The launchers pass command-line variables as strings. Values such as `true` and `false` were substituted into `Skip If    not ${VARIABLE}`, producing Python expressions such as `not true`. Python recognizes `True` and `False`, not lowercase names, so suite setup failed before connection.
2. The Windows BAT runner hard-coded `HIL_ENABLE:true`, including simulator mode.

## Implementation changes

- Added `Normalize Runtime Boolean Variables` to the self-check resource.
- Converted `HIL_ENABLE`, `ALLOW_RESET`, and `ALLOW_ACTIVE_OUTPUT` with Robot Framework's `Convert To Boolean` before use.
- Changed guards to typed expression variables: `not $HIL_ENABLE`, `not $ALLOW_RESET`, and `not $ALLOW_ACTIVE_OUTPUT`.
- Corrected BAT simulator/HIL selection and expected simulated module handling.
- Added RFDS-019 static checks for normalization and unsafe lowercase-string guard patterns.
- Hardened the guarded hardware example with the same conversion rule.

## Public API and protocol impact

No public keyword, argument, return value, SCPI command, response parser, or module capability changed. The defect was in the Robot execution harness and runner integration.

## Evidence from the reported run

The supplied run showed 21 suite tests failing with `NameError: name 'true' is not defined`, zero protocol trace records, and no instrument connection. This confirms the failure occurred before the driver reached the device.

## Hardware-validation status

**HIL RETEST REQUIRED.** The pre-connection blocker is corrected. The N6700/N6775A suite must now be rerun to expose any device- or firmware-specific protocol differences.
