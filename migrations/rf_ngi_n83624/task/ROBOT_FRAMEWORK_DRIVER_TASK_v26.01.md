# Task: Robot Framework Driver for NGI N83624

**Task revision:** 26.01-final  
**Date:** 2026-07-18  
**Target package:** `rf_ngi_n83624_v26.01.zip`  
**Required internal repository root:** `rf_ngi_n83624/`

## 1. Objective

Create a maintainable, safety-oriented Robot Framework library based on the supplied `ngi_n83624` Python driver. The deliverable shall expose stable Robot keywords for common N83624 workflows while retaining the typed Python driver as the SCPI and transport implementation layer.

The package must support offline verification without hardware and define a separate, explicit qualification process for the exact N83624 model, firmware, fixture, DUT, and bench safety system.

## 2. Mandatory package structure

```text
rf_ngi_n83624/
├── rf_ngi_n83624/          Robot Framework Python library
├── ngi_n83624/             supplied core driver, reviewed and corrected
├── examples/               at least 10 Robot suites
├── scripts/                Windows and Linux setup/test/example/build scripts
├── tests/                  Python unit tests and Robot acceptance tests
├── task/                   final task and task readiness review
├── history/                change history for every release
├── review/                 implementation review and fix records
├── guide/                  PyCharm, Robot Framework, safety, and HIL setup
├── docs/                   GitHub Pages/MkDocs content
├── .github/workflows/      CI and Pages workflows
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── mkdocs.yml
└── LICENSE
```

No `src/` directory is permitted.

## 3. Versioning and packaging

1. ZIP filename shall be `rf_ngi_n83624_v26.01.zip`.
2. ZIP shall contain exactly one top-level folder named `rf_ngi_n83624`.
3. Human-facing release label shall be `v26.01`.
4. Python distribution version shall be PEP 440-compatible `26.1`.
5. The Python import shall be `rf_ngi_n83624`.
6. The primary Robot import shall be:

```robot
Library    rf_ngi_n83624.library.NGI_N83624
```

## 4. Architecture

### 4.1 Layers

1. **Robot Framework layer**
   - Keyword names, aliases, Robot-friendly argument conversion, assertions, polling, audit logging, and cleanup.
2. **Typed Python driver layer**
   - Transport, SCPI formatting/parsing, enums, validation, channel API, and emulator.
3. **Transport layer**
   - TCP, UDP, channel-specific UDP, RS232, and test emulator.
4. **Instrument and bench layer**
   - N83624 hardware, independent measurement, interlocks, DUT, and fixture.

### 4.2 Design constraints

- Robot keywords shall not duplicate SCPI formatting logic.
- High-level keywords shall call typed Python methods.
- Raw SCPI shall be an explicitly guarded escape hatch.
- Multiple instruments/connections shall be supported through aliases.
- All public Robot arguments shall accept normal Robot scalar strings and typed values.
- Returned dataclasses/enums shall be converted to Robot dictionaries, lists, strings, booleans, integers, or floats.

## 5. Required connection keywords

- `Open N83624 TCP Connection`
- `Open N83624 UDP Connection`
- `Open N83624 Channel UDP Connection`
- `Open N83624 Serial Connection`
- `Open N83624 Emulator`
- `Switch N83624 Connection`
- `Get Active N83624 Connection`
- `List N83624 Connections`
- `Close N83624 Connection`
- `Close All N83624 Connections`
- `Identify N83624`

Each open keyword shall:

1. Reject duplicate/empty aliases.
2. Open and optionally verify identity.
3. Configure software limits and safety policy.
4. Register the connection only after successful connect.
5. Close the transport after failed initialization.
6. Optionally configure a JSONL audit path.

## 6. Safety requirements

### 6.1 Output arming

Output enable shall be blocked unless all conditions hold:

1. Channel is in range 1..24.
2. Effective maximum voltage and current limits are finite.
3. Channel was armed with exact confirmation text `ENABLE OUTPUT`.
4. Configuration values pass typed-driver validation.

Changing channel limits or recovering a connection shall disarm affected outputs.

Required keywords:

- `Set Channel Safety Limits`
- `Get Channel Safety Limits`
- `Arm Channel Output`
- `Disarm Channel Output`
- `Disarm All Channel Outputs`
- `Channel Output Should Be Armed`

### 6.2 Shutdown

- `Disable Channel Output` must never require arming.
- `All N83624 Outputs Off` shall attempt all 24 channels.
- One failed channel command shall not prevent attempts on remaining channels.
- Failures shall be aggregated and raised after all attempts.
- Safe close shall close the transport even when output-off reports an error.
- Suite/library cleanup shall attempt all open sessions.
- Cleanup failures shall be logged without hiding an existing Robot failure.

### 6.3 Raw SCPI

- Raw query/write shall be disabled by default.
- Enabling requires exact text `ENABLE RAW SCPI`.
- Documentation must state that raw writes bypass typed validation and output arming.

### 6.4 Safety boundary

Documentation shall explicitly state that software cannot replace:

- emergency stop;
- fusing/contactors;
- independent voltage/current monitoring;
- DUT/fixture risk analysis;
- hardware interlocks;
- discharge/energy controls;
- real-hardware validation.

## 7. Operating-mode keywords

Required:

- `Set Channel Mode`
- `Get Channel Mode`
- `Configure Source Mode`
- `Configure Charge Mode`
- `Configure SOC Profile`
- `Configure Sequence Profile`
- `Enable Channel Output`
- `Disable Channel Output`
- `Get Channel Output State`
- `Channel Output Should Be On`
- `Channel Output Should Be Off`

Enum inputs shall accept names and documented integer values.

SOC and sequence steps shall accept Robot lists of dictionaries and JSON lists. Missing required fields, malformed JSON, invalid ranges, empty profiles, and non-finite numbers shall fail before unsafe output use.

## 8. Measurement and assertion keywords

Required:

- `Measure Channel Voltage`
- `Measure Channel Current`
- `Measure Channel Power`
- `Measure Channel Resistance`
- `Measure Channel Capacity`
- `Measure Channel`
- `Measure Voltage Channels`
- `Channel Voltage Should Be Within`
- `Channel Current Should Be Within`
- `Wait Until Channel Voltage Is Within`
- `Wait Until Channel Current Is Within`
- `Get Channel Status`
- `Get Channel Event`
- `Get Channel Configuration`

Polling shall use a monotonic clock and reject negative tolerance/timeout or non-positive interval.

## 9. Protection, acquisition, and supervision

Required:

- `Set Channel Protection Limits`
- `Set Channel Capture Rate`
- `Get Channel Capture Rate`
- `Start N83624 Heartbeat`
- `Stop N83624 Heartbeat`
- `Get N83624 Communication Health`
- `Recover N83624 Connection`

Recovery shall clear output arming because physical state may be unknown after communication loss.

## 10. Emulator requirements

The emulator shall support:

- identity and operation-complete queries;
- channel source/charge/output configuration;
- channel measurements;
- aggregate voltage/current/power queries for selected channels;
- deterministic measurement injection;
- command-order capture;
- SOC and sequence command recording.

Emulator documentation must state that it is not hardware qualification.

## 11. Audit logging

When configured, write JSONL records containing:

- UTC timestamp;
- library release;
- connection alias;
- action;
- relevant channel/configuration/result fields;
- cleanup error where applicable.

At minimum log connection open/close, limit changes, arm/disarm, output actions, mode/profile configuration, heartbeat, recovery, and raw SCPI.

## 12. Tests

### 12.1 Python unit tests

Cover at minimum:

1. Emulator connect and identity.
2. Robot data conversion.
3. Output blocked before arming.
4. Output enabled after finite limits and arming.
5. Limit changes disarm output.
6. Raw SCPI guard.
7. SOC/sequence JSON parsing.
8. Audit records.
9. Multi-channel emulator queries.
10. All-channel shutdown continues after injected channel failure.
11. Communication observations use a monotonic clock.

### 12.2 Robot acceptance tests

Must run offline and cover:

- identity;
- source configuration;
- output arming/on/off;
- measurement assertion;
- SOC profile;
- sequence profile;
- suite teardown.

### 12.3 Hardware tests

Create a marked hardware test plan; do not run automatically in CI. Include:

- identity and firmware capture;
- command-by-command verification;
- independent DMM/DAQ comparison;
- normal and exceptional shutdown;
- network cable removal;
- serial/TCP/UDP framing;
- watchdog/reconnect behavior;
- 8-hour soak;
- 1000-cycle output test;
- audit evidence retention.

## 13. Documentation and examples

Deliver:

- README with install, import, safety, examples, test/build commands, layout, and status.
- GitHub Pages with installation, keywords, safety, examples, HIL qualification, and release notes.
- PyCharm/Robot Framework setup guide for Windows and Linux.
- Hardware qualification guide.
- At least 10 Robot examples; target 14.
- Generated Libdoc HTML keyword reference.
- History and implementation review for v26.01.

## 14. Scripts

Provide PowerShell, BAT where practical, and Bash scripts for:

- virtual environment setup;
- complete test run;
- individual example run;
- offline example run;
- wheel/sdist build.

Scripts shall fail fast and use the repository-local `.venv`.

## 15. CI and release checks

GitHub Actions shall test Windows and Linux with supported Python versions and run:

1. editable install;
2. Python unit tests;
3. Robot acceptance tests;
4. Ruff static analysis;
5. wheel and sdist build;
6. Robot result artifact upload.

GitHub Pages workflow shall build and deploy MkDocs from `main`.

## 16. Acceptance criteria

The task is complete only when:

- [x] Required package naming and root structure are satisfied.
- [x] No `src/` layout is used.
- [x] At least 10 Robot examples exist.
- [x] Connection, safety, output, mode, measurement, protection, heartbeat, recovery, and raw SCPI keywords exist.
- [x] Output arming and finite-limit gates are tested.
- [x] All-channel shutdown is best-effort and tested with fault injection.
- [x] Python tests pass.
- [x] Robot acceptance tests pass.
- [x] Offline examples pass.
- [x] Static analysis passes.
- [x] Wheel and source distributions build.
- [x] README, Pages, guides, task, history, and review are present.
- [ ] Real N83624 HIL qualification is complete.

The final unchecked item is a deployment qualification gate, not an offline software-generation defect. The release must remain labeled “hardware qualification required” until it is completed.
