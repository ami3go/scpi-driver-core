# Release History — v26.01

**Release date:** 2026-07-17  
**Archive:** `rf_keysight_n6700_v26.01.zip`  
**Internal root:** `rf_keysight_n6700/`  
**Python package version:** `26.1.0`

## Functional implementation

- Added `KeysightN6700Library` as a Robot Framework adapter over the existing typed Python driver.
- Added simulator, VISA, and raw Ethernet connection keywords.
- Added named session support for multiple N6700 mainframes.
- Added PSU, SMU, electronic-load, measurement, protection, status, self-test, and raw SCPI keywords.
- Added engineering-unit parsing and Robot-friendly result serialization.
- Added safe shutdown on disconnect and suite teardown.
- Added measurement assertions and wait/polling keywords.
- Retained the original `keysight_n6700` Python driver, transport layer, capability model, and simulator.

## Package-format update

- Renamed the release archive to the project convention: `rf_keysight_n6700_v26.01.zip`.
- Changed the fixed internal repository folder to `rf_keysight_n6700/`.
- Consolidated Robot and Python examples under `examples/`.
- Added `history/`, `review/`, and `guide/` folders.
- Added Windows BAT, PowerShell, and POSIX shell scripts for setup, examples, tests, documentation, and package builds.
- Updated the root README with the required layout, commands, safety model, and version policy.
- Added a complete PyCharm and Robot Framework setup guide.
- Added GitHub Pages source navigation and an automated Pages deployment workflow.
- Added release manifest and regenerated checksums.
- Cleaned legacy Python style findings and strengthened driver/transport typing so repository-wide Ruff and strict Mypy checks pass.

## Validation performed

- Python unit tests against the simulator.
- Robot Framework simulator smoke tests.
- Full Robot Framework example suite, with hardware examples safely skipped without supplied hardware variables.
- Ruff static linting.
- Mypy static type checking.
- Wheel and source-distribution build.
- Robot Framework Libdoc generation.
- MkDocs strict documentation build.
- Clean virtual-environment installation and simulator execution.
- Final ZIP structure and checksum verification.

## Known limitations

- Real-instrument acceptance requires the user's N6700 mainframe and installed module set.
- Hardware-output examples are intentionally guarded and must not be run without reviewed limits and a safe fixture.
- Electronic-load functions are blocked for module models that have not been explicitly verified by the driver capability policy.
