# RF Keysight N6700

Production-oriented Robot Framework library and typed Python driver for Keysight/Agilent N6700-series modular power systems.

| Item | Value |
|---|---|
| Release package | `rf_keysight_n6700_v26.09.zip` |
| Fixed repository folder | `rf_keysight_n6700/` |
| Python distribution | `robotframework-keysight-n6700` |
| Python version | `26.9.0` |
| Robot Framework library | `KeysightN6700Library` |
| Release date | 2026-07-24 |

The repository deliberately uses a root package layout. There is no `src/` directory.

## Features

- Robot Framework keywords for power-supply, SMU, and verified electronic-load channels.
- VISA/USB, raw Ethernet socket, and bundled simulator connections.
- Multiple named instrument sessions.
- Engineering-value parsing, including `12V`, `500mA`, `10uA`, `2.2k`, and `500ms`.
- Safe, non-invasive connection by default.
- Optional automatic output shutdown during disconnect and suite teardown.
- Voltage, current, and power measurements with built-in assertions and polling.
- Protection handling, SCPI error checks, self-test, module discovery, and raw SCPI access.
- Robot-friendly dictionary and list return values.
- Fourteen Robot Framework examples and seventeen executable Python driver examples plus CLI notes.
- Simulator-based unit and Robot Framework acceptance tests.
- Generated Robot Framework Libdoc and MkDocs/GitHub Pages documentation.
- RFDS-017 AI driver contract with one machine-readable capability per Robot keyword.
- RFDS-018 fail-closed test-bench contract template for multi-driver planning.
- Deterministic AI-contract generation, lock hashes, package checks, and CI drift detection.
- RFDS-019 N6775A full self-check with 63-keyword inventory, 45 protocol vectors, 18 explicit exclusions, SCPI command/response tracing, recovery checks, and machine-readable evidence.

## Required project layout

```text
rf_keysight_n6700/
├── ai/                       # RFDS-017 driver contract and deterministic lock
├── standards/                # Supplied RFDS project source specifications
├── system_ai_contract.yaml   # RFDS-018 bench contract template
├── KeysightN6700Library/     # Robot Framework adapter
├── keysight_n6700/           # Typed Python driver and simulator
├── examples/
│   ├── robot/                # 14 Robot Framework examples
│   └── python/               # Python driver examples
├── scripts/                  # Setup, test, example, docs, and build launchers
├── history/                  # Release-by-release change descriptions
├── review/                   # Release code and package reviews
├── guide/                    # PyCharm, Robot Framework, and hardware setup guides
├── docs/                     # GitHub Pages / MkDocs source and generated Libdoc
├── resources/                # Reusable Robot Framework resources
├── tests/                    # Unit, Robot, and hardware acceptance tests
├── .github/workflows/        # CI and GitHub Pages deployment
├── pyproject.toml
└── README.md
```

## Quick start on Windows

From PowerShell or Command Prompt in the unpacked repository:

```bat
scripts\setup_venv.bat
scripts\run_example.bat 01_simulator_smoke.robot
```

Run every simulator-compatible Robot example:

```bat
scripts\run_all_examples.bat
```

Run validation:

```bat
scripts\run_tests.bat
```

Verify the required project package structure:

```bat
scripts\verify_package.bat
```

PowerShell-native launchers are also provided, for example:

```powershell
.\scripts\setup_venv.ps1
.\scripts\run_example.ps1 02_power_supply_basic.robot
```

Linux/macOS:

```bash
./scripts/setup_venv.sh
./scripts/run_example.sh 01_simulator_smoke.robot
```

## Install with pip

```bash
python -m pip install .
```

For systems without a vendor VISA installation:

```bash
python -m pip install ".[visa-py]"
```

For development and documentation:

```bash
python -m pip install -e ".[dev,docs]"
```

## Minimal Robot Framework test

```robotframework
*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Configure And Measure Channel 1
    Configure N6700 Power Supply Channel    1    12V    500mA    output=${TRUE}
    N6700 Voltage Should Be    1    12V    50mV
    ${measurement}=    Measure N6700 Channel    1
    Log    ${measurement}
    Turn Off N6700 Output    1
```

The bare `Library    KeysightN6700Library` import also still works for
backward compatibility, but `rf_keysight_n6700.KeysightN6700Library` is the
recommended form — it matches the `rf_<device>.<Device>Library` convention
used across this repository's drivers.

## Real instrument connection

USB VISA / USBTMC:

```robotframework
Connect To N6700 Via USB    USB0::0x0957::0x0907::MY43014421::INSTR    main
```

VISA:

```robotframework
Connect To N6700 Via VISA    TCPIP0::192.168.1.50::inst0::INSTR    main
```

Raw Ethernet socket:

```robotframework
Connect To N6700 Via Ethernet    192.168.1.50    5025    main
```

Named sessions can be selected explicitly:

```robotframework
Select N6700    main
```


## N6775A full self-check

The package contains a hardware-safe RFDS-019 suite for a Keysight N6775A module. It verifies identity and module discovery, common SCPI commands, voltage/current/protection configuration with read-back, measurements, error handling, recovery, unsupported SMU/load calls, safe shutdown, disconnect/reconnect, and transport-boundary command/response evidence.

The default profile keeps the output OFF. Reset and active-output tests are separate opt-in gates.

```powershell
.\scripts\run_n6775a_self_check.ps1 `
  -Resource "USB0::0x0957::0x0907::MY43014421::INSTR" `
  -ConnectionType usb `
  -Channel 1
```

The USB resource above is the default N6775A self-check profile, so this shorter command is equivalent:

```powershell
.\scripts\run_n6775a_self_check.ps1
```

Raw TCP socket example:

```powershell
.\scripts\run_n6775a_self_check.ps1 `
  -Resource "192.168.0.50" `
  -ConnectionType ethernet `
  -Port 5025 `
  -Channel 1
```

Results are stored below `results/call_protocol_conformance/keysight_n6700/<UTC timestamp>/` and include Robot reports, protocol traces, environment/device identity, keyword coverage, vector results, exclusions, and a Markdown summary. See [N6775A self-check guide](docs/n6775a_self_check.md).

## Logging and evidence

Every SCPI write/query — from every typed keyword and from raw `Query N6700 SCPI` — passes through one transport-boundary choke point in `keysight_n6700/driver.py`. Passing `audit_log_path` when connecting records a `.jsonl` trace of that session's complete command/response history, timestamps, durations, and errors, independent of any formal test run:

```robotframework
Connect To N6700    USB0::0x0957::0x0907::MY43014421::INSTR    main
...    audit_log_path=${OUTPUT DIR}/n6700_audit.jsonl
```

This is the tool for "what did this session actually send/receive and when" troubleshooting questions. See [Audit logging](docs/audit_logging.md) for the record schema and how it relates to the RFDS-019 self-check's own evidence bundle (above) — the two are complementary: `audit_log_path` traces one session, the self-check proves every keyword still reaches the instrument correctly.

## Safety model

The library constructor supports:

```robotframework
Library    rf_keysight_n6700.KeysightN6700Library    auto_shutdown=${TRUE}    strict_errors=${TRUE}
```

- `auto_shutdown=${TRUE}` attempts to disable controllable outputs and load inputs before closing a connection and at suite end.
- `strict_errors=${TRUE}` checks the SCPI error queue after typed mutating keywords.
- Combined configuration keywords leave outputs disabled unless explicitly enabled.
- Protection clearing turns the affected output or input off first.
- Raw SCPI keywords bypass typed capability checks and require reviewed commands.

Software controls do not replace current limiting, interlocks, fixture protection, emergency stop circuitry, or a reviewed hardware test plan.


## AI test-planning contracts

The package includes deterministic, machine-verifiable contracts based on the supplied project source standards:

- `ai/keysight_n6700_ai_contract.yaml` implements RFDS-017 v3.0 and contains one capability record for each of the 63 Robot Framework keywords.
- `ai/keysight_n6700_ai_contract.lock` binds the contract to the exact keyword list, library source, generator, driver version, and RFDS-018 contract.
- `system_ai_contract.yaml` implements RFDS-018 v1.0 as a safe standalone bench template. It blocks energization until site-specific module map, topology, polarity, DUT limits, safety zones, interlock, and stabilization values are configured.

Regenerate or check the contracts:

```bash
python scripts/generate_ai_contract.py
python scripts/generate_ai_contract.py --check
```

An AI agent should use the driver contract directly, but it must merge it into a completed, approved bench contract before generating executable energizing tests.

## Documentation

- [Installation guide](guide/installation.md)
- [PyCharm and Robot Framework setup](guide/pycharm_robot_framework_setup.md)
- [Writing and running Robot tests](guide/writing_robot_tests.md)
- [Hardware connection guide](guide/hardware_connection.md)
- [Robot Framework library guide](docs/robot_framework/guide.md)
- [Keyword summary](docs/robot_framework/keyword_summary.md)
- [Examples index](examples/README.md)
- [Project package requirements](PROJECT_REQUIREMENTS.md)
- [AI driver and bench contracts](docs/ai_contracts.md)
- RFDS-017 contract: `ai/keysight_n6700_ai_contract.yaml`
- RFDS-018 bench template: `system_ai_contract.yaml`
- [Release history](history/v26.09.md)
- [Release code review](review/v26.09_code_review.md)
- Generated Libdoc: `docs/KeysightN6700Library.html`

Build the GitHub Pages site locally:

```bash
scripts/build_docs.sh
```

## Compatibility

- Python 3.10 through 3.13
- Robot Framework 7.x and 8.x
- PyVISA 1.14+
- Keysight/Agilent N6700-family mainframes represented by the driver capability map

Electronic-load commands remain intentionally blocked for unverified physical load modules. The bundled `SIM_LOAD` module is available for automated tests.

## Release policy

Future archives use the pattern:

```text
rf_keysight_n6700_vYY.RR.zip
```

The internal root remains exactly:

```text
rf_keysight_n6700/
```

This lets a newer release replace an older unpacked repository without changing project paths.

## License

MIT. See [LICENSE](LICENSE).

> **N6775A power measurement:** the module does not support direct `MEAS:POW?`. The library reads `MEAS:VOLT?` and `MEAS:CURR?`, calculates watts, and reports `power_source=calculated`.
