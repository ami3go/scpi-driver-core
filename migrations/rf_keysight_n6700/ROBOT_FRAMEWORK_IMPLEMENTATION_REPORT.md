# Robot Framework Implementation Report

## Release

- Public release label: **v26.09**
- Release archive: `rf_keysight_n6700_v26.09.zip`
- Fixed internal root: `rf_keysight_n6700/`
- Python distribution version: **26.9.0**
- Robot library import: `KeysightN6700Library`
- Library scope: `SUITE`
- Exposed Robot keywords: **63**

## Architecture decision

An adapter was implemented over the existing driver instead of copying SCPI logic into the Robot layer. The underlying `keysight_n6700` package remains responsible for transport, simulator behavior, channel type selection, module capability checks, measurements, protection handling, and shutdown. The Robot adapter is responsible for keyword naming, argument conversion, named sessions, assertions, polling, dictionary serialization, logging, and suite cleanup.

## Implemented areas

| Area | Status | Notes |
|---|---:|---|
| VISA/USB connection | Implemented | Uses PyVISA transport |
| Raw Ethernet connection | Implemented | Default port 5025 |
| Simulator connection | Implemented | Four-channel bundled simulator |
| Named sessions | Implemented | Connect, select, list, and disconnect aliases |
| Automatic cleanup | Implemented | Best-effort shutdown before close and at suite end |
| Module discovery | Implemented | Robot-friendly capability dictionaries |
| PSU configuration | Implemented | Voltage, current limit, OVP, OCP, output state |
| SMU configuration | Implemented | Voltage/current priority and supported off mode |
| Electronic load | Implemented with driver limits | Real unverified load modules remain blocked |
| Measurements | Implemented | Voltage, current, power, one/all channels |
| Assertions | Implemented | Voltage/current/power and output state |
| Polling | Implemented | Wait for voltage range with timeout |
| Protection | Implemented | Status, safe clear, all-channel shutdown |
| SCPI errors | Implemented | Strict post-write checks and explicit queue keywords |
| Raw SCPI | Implemented | Documented as advanced capability-bypassing access |
| Documentation | Implemented | Markdown, 14 examples, resource file, generated Libdoc HTML |
| Packaging | Implemented | Wheel and source distribution |
| AI contracts | Implemented | RFDS-017 per-keyword driver contract, lock, and RFDS-018 fail-closed bench template |

## Validation results

- Python regression tests: **26 passed**, 1 hardware test deselected.
- Python compile check: **passed** for the library, driver, scripts, and unit tests.
- RFDS-019 static conformance: **32 passed**.
- Project package source validation: **103 passed**.
- Installed-wheel simulator/import smoke test: **passed**.
- Generated Libdoc metadata: **63 keywords**, version **26.9.0**, scope **SUITE**.
- Physical USB opening and the Robot hardware suite remain pending on the real Windows/VISA bench.
- Ruff, Mypy, MkDocs, and the full Robot simulator suite were not rerun in this constrained build environment because those external tool packages were unavailable; the corresponding source configurations and suites are retained.

## Known limitations inherited from the driver

- Real electronic-load SCPI commands are intentionally blocked until verified against an exact module and official command map.
- Remote/local control is transport-specific and currently supported only by the simulator implementation.
- Operation status and questionable status support is limited by the current driver command coverage.
- Real hardware acceptance still requires execution with the user's exact mainframe, installed modules, VISA backend, wiring, loads, and safety fixture.

## Recommended hardware validation sequence

1. Run `examples/robot/10_real_hardware_readonly.robot` first.
2. Confirm identity, channel count, module models, serials, and options.
3. Review fixture current limits, OVP, emergency stop, and load ratings.
4. Run the guarded output example with a low voltage/current limit.
5. Verify teardown turns outputs off after both passing and deliberately failing test cases.
6. Add module-specific acceptance tests for each installed N67xx module.
