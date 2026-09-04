# Changelog

## v26.09 / 26.9.0 — 2026-07-24

### N6775A measurement-capability and self-check correction

- Corrected N6775A capability metadata: direct `MEAS:POW?` is not supported by N677x modules.
- Power is now calculated from `MEAS:VOLT?` and `MEAS:CURR?` for N673x/N674x/N675x/N677x modules.
- Direct `MEAS:POW?` remains enabled only for N676x and N678x modules, matching the programmer reference.
- Prevented unsupported power queries from timing out and contaminating the SCPI error queue with `+310` and `-420` errors.
- Normalized quoted-empty channel option responses to an empty option list.
- Converted the self-check channel variable to an integer and removed a Robot variable-name collision that overwrote `${CHANNEL}` with a measurement dictionary.
- Added simulator and unit regressions that reject unsupported direct power measurement on N6775A.

## v26.08 / 26.8.0 — 2026-07-24

### N6775A stale-error startup recovery

- Fixed real-device self-check startup when the N6700 error queue contains errors from a previous failed run.
- Enabled explicit error draining during the self-check connection profile.
- Added `*CLS` and an empty-queue assertion before the first strict-checked output command.
- Added simulator regression coverage and RFDS-019 static checks for startup ordering.
- No N6775A voltage, current, output, OVP, OCP, measurement, or protection SCPI header changed.

## v26.07 / 26.7.0 — 2026-07-24

### N6775A manual-command correction

- Confirmed the supplied USB VISA resource and N6700B/N6775A discovery are working.
- Corrected OCP commands to `CURR:PROT:STAT <Bool>,(@ch)` and `CURR:PROT:STAT? (@ch)`.
- Replaced invalid `OUTP:PROT?` polling with `STAT:QUES:COND? (@ch)`.
- Added Questionable Condition bit decoding and mandatory channel lists for status queries.
- Hardened the simulator and RFDS-019 protocol vectors against invalid SCPI abbreviations.
- Added exact-command and protection-decoding regression tests.

## v26.06 / 26.6.0 — 2026-07-24

- Added `Connect To N6700 Via USB`.
- Added default N6775A USB resource `USB0::0x0957::0x0907::MY43014421::INSTR` to self-check runners.
- Added RFDS-019 USB connection vector, unit test, documentation, and release records.

## v26.05 / 26.5.0 — 2026-07-24

### N6775A self-check execution correction

- Fixed suite setup failure when command-line boolean variables were supplied as lowercase strings such as `true` and `false`.
- Added explicit Robot `Convert To Boolean` normalization before any HIL, reset, or output guard is evaluated.
- Changed guard expressions to use Robot's typed `$variable` expression form.
- Fixed the Windows BAT runner so simulator mode no longer forces `HIL_ENABLE=true`.
- Hardened the guarded real-hardware example against the same command-line boolean conversion issue.
- Extended the RFDS-019 static validator to reject this regression in future releases.
- No public Robot keyword, SCPI serialization, transport behavior, or safety limit changed.

## v26.04 / 26.4.0 — 2026-07-24

### N6775A RFDS-019 self-check

- Added a 21-case Robot Framework hardware self-check for the Keysight N6775A module.
- Added complete 62-keyword inventory, 44 protocol vectors, and 18 explicit model/profile exclusions.
- Added transport-boundary JSONL capture of each SCPI write, query, response, exception, and duration.
- Added safe read-back verification for voltage, current, OVP, OCP, output state, measurements, protection clearing, and shutdown.
- Added invalid-command, invalid-argument, unsupported-feature, disconnect/reconnect, and communication-recovery checks.
- Added opt-in reset and active-output vectors; both are disabled by default.
- Added Windows BAT/PowerShell and POSIX runners with timestamped RFDS-019 evidence.
- Added static conformance validator and evidence postprocessor.
- Updated RFDS contracts, package checks, documentation, history, reviews, distributions, and release metadata.

## v26.03 / 26.3.0 — 2026-07-21

### RFDS AI contract update

- Added RFDS-017 v3.0 driver contract and deterministic lock.
- Added one complete capability record for every one of the 62 public Robot Framework keywords.
- Added RFDS-018 v1.0 bench contract template with fail-closed UNKNOWN handling.
- Added deterministic contract generation and source/contract drift checks.
- Extended package verification, tests, CI, build scripts, documentation, and release records to enforce AI-contract conformance.
- Added source-standard copies for RFDS-017 and RFDS-018.
- No intentional SCPI, transport, module-support, safety-default, or public keyword behavior change.

## v26.02 / 26.2.0 — 2026-07-17

### Project package integrity update

- Added an explicit project-requirements mapping and machine-readable release metadata.
- Added source-tree and final-ZIP package verification using only the Python standard library.
- Added BAT, PowerShell, and POSIX verifier launchers.
- Changed release creation to derive `vYY.RR` from `pyproject.toml`, eliminating an independent hard-coded release value.
- Added post-build checks for archive name, single fixed root, required folders/files, at least ten examples, current history/review records, GitHub Pages, IDE guidance, build artifacts, and no `src/` layout.
- Added unit-test and CI enforcement of the project package standard.
- Updated README, GitHub Pages, manifests, release records, version metadata, distributions, Libdoc, and checksums.
- Retained v26.01 history and review records.

### Driver behavior

- No intentional SCPI, safety-policy, transport, or public Robot Framework keyword behavior change.

## v26.01 / 26.1.0 — 2026-07-17

### Robot Framework implementation

- Added `KeysightN6700Library`, a static Robot Framework adapter.
- Added VISA, raw Ethernet socket, and simulator connection keywords.
- Added multiple named session support.
- Added safe automatic shutdown on disconnect and suite end.
- Added PSU, SMU, electronic-load, measurement, protection, error, and raw SCPI keywords.
- Added engineering-unit and timeout parsing.
- Added Robot-friendly dictionary serialization.
- Added built-in measurement assertions and voltage range polling.
- Added fourteen Robot Framework examples and reusable resource keywords.
- Added simulator-backed Python and Robot tests.
- Retained and packaged the original typed `keysight_n6700` Python driver.

### Project package compliance update

- Renamed archive to `rf_keysight_n6700_v26.01.zip`.
- Changed fixed internal root to `rf_keysight_n6700/`.
- Consolidated examples into `examples/robot/` and `examples/python/`.
- Added release history and code review folders.
- Added PyCharm, Robot Framework, installation, test-writing, and hardware guides.
- Added BAT, PowerShell, and shell launchers for setup, examples, tests, docs, and builds.
- Updated README, GitHub Pages source, CI, and Pages deployment workflow.
- Added release manifest and regenerated build checksums.
- Resolved repository-wide Ruff findings and strict Mypy errors in the imported driver, simulator, transport, tests, and examples.

## 0.1.1

- Original Python driver release imported as the implementation base.
