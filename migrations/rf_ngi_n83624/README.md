# rf-ngi-n83624

Robot Framework library for the **NGI N83624 24-channel battery/cell simulator**, built on the supplied typed Python SCPI driver.

Release label: **v26.02**  
Python package version: **26.2**.

## Capabilities

- TCP, UDP, channel-specific UDP, RS232, and deterministic emulator sessions.
- Multiple named connections with active-session switching.
- Source, charge, SOC, and sequence configuration keywords.
- Voltage/current/power/resistance/capacity measurements and assertions.
- OCP, OVP, OPP, capture-rate, heartbeat, recovery, and communication-health keywords.
- Explicit output arming gate plus finite voltage/current limit enforcement.
- Guarded raw SCPI access.
- Best-effort all-channel safe shutdown and automatic suite cleanup.
- Optional JSONL audit log for safety-relevant operations, plus an always-on-by-default
  RFDS-008 structured evidence layer (per-alias run directory, protocol trace, integrity
  manifest) — see [Logging and evidence](#logging-and-evidence) below.
- An RFDS-019 real-hardware keyword conformance suite exercising all 62 public keywords —
  see [Hardware tests](#hardware-tests) below.
- Fourteen Robot Framework examples, unit tests, Robot acceptance tests, GitHub Actions, GitHub Pages, PyCharm setup guide, history, and implementation review.

## Installation

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev,docs]"
```

Linux/macOS:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e '.[dev,docs]'
```

## Robot Framework import

```robot
*** Settings ***
Library    rf_ngi_n83624.NGI_N83624Library
```

## Offline smoke example

```robot
*** Settings ***
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    emu    max_voltage_v=5.0    max_current_ma=500
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Safe Source Cycle
    Configure Source Mode    1    3.7    100    AUTO    output=${False}
    Arm Channel Output       1    ENABLE OUTPUT
    Enable Channel Output    1
    Channel Output Should Be On    1
    Disable Channel Output   1
```

## Real TCP connection

```robot
Open N83624 TCP Connection
...    bench
...    host=192.168.0.123
...    port=7000
...    max_voltage_v=5.0
...    max_current_ma=500
...    audit_log_path=${OUTPUT DIR}${/}ngi_audit.jsonl
```

Output enabling is blocked until the channel has finite voltage/current limits and is explicitly armed with `Arm Channel Output    <channel>    ENABLE OUTPUT`.

## Logging and evidence

Every keyword call is recorded as structured, correlated RFDS-008 evidence —
arguments, duration, result/failure, and the underlying SCPI write/query
traffic — written per connection alias to
`results/session/rf_ngi_n83624/<run>/` (override with the `RFDS_EVIDENCE_ROOT`
environment variable). This is on by default and independent of the existing
opt-in `audit_log_path` JSONL audit log; pass `evidence_enabled=${FALSE}` to
the `Library` import to disable it, or call `Export Diagnostic Bundle` to zip
a given alias's current run for a bug report. See
[docs/logging-and-evidence.md](docs/logging-and-evidence.md) for the full
evidence layout and [guide/EVIDENCE_AND_DIAGNOSTICS.md](guide/EVIDENCE_AND_DIAGNOSTICS.md)
for a task-oriented "my test failed, now what" walkthrough. Validate a run's
integrity (hashes, JSONL sequencing) with:

```console
python scripts/validate_evidence.py results/session/rf_ngi_n83624/<run>/
```

## Hardware tests

`tests/hardware/verify_all_keywords.robot` is an RFDS-019 real-hardware
keyword-conformance suite: one test case per public keyword (62 total,
KW-001..KW-062), run against a real N83624 over TCP by default. It is tagged
`hardware` and does not run in CI:

```console
robot --outputdir build/robot -v HOST:192.168.0.123 -v PORT:7000 tests/hardware/verify_all_keywords.robot
```

Every channel stays disarmed/output-off for the whole suite unless
`-v ALLOW_OUTPUT_ON:True` is passed, and settings that can "break
communication" (IP address, serial baud rate, LAN connection type) are never
touched. UDP-specific test cases are tagged `udp`; exclude them with
`--exclude udp` on a bench/proxy that only reaches the instrument over TCP.
`-v SERIAL_PORT:<port>` additionally exercises the RS232 connection keyword.
See the suite's own `Documentation` for the full list of variables and what
each safety gate unlocks.

**This is keyword-callability and SCPI-protocol conformance (RFDS-019
scope), not the full HIL qualification described in
[guide/HARDWARE_QUALIFICATION.md](guide/HARDWARE_QUALIFICATION.md)** — it
does not replace Gates H4 (controlled output enable across representative
setpoints), H5 (protection), H6 (exceptional shutdown), H7 (UDP
characterization under packet loss), or H8 (endurance). It's a fast, safe
first check that every keyword actually reaches the instrument and gets a
sane response back, useful on its own and as a precursor to the full
qualification gates.

## Run tests

Windows:

```powershell
.\scripts\run_tests.ps1
```

Linux/macOS:

```bash
./scripts/run_tests.sh
```

Direct commands:

```bash
python -m pytest                                                      # unit + evidence tests
robot --outputdir build/robot tests/robot/acceptance.robot             # offline Robot acceptance
robot --outputdir build/robot --exclude hardware --exclude udp \
    tests/hardware/verify_all_keywords.robot                          # dry-run friendly; use --dryrun to skip execution entirely
ruff check .
python -m build
```

Run the real-hardware conformance suite itself only against actual bench
hardware (see [Hardware tests](#hardware-tests) above) — the `--exclude
hardware` form above is for confirming the suite still parses/imports
cleanly in CI, not for exercising it.

## Run examples

```powershell
.\scripts\run_example.ps1 .\examples\01_emulator_smoke.robot
```

```bash
./scripts/run_example.sh examples/01_emulator_smoke.robot
```

Hardware examples contain bench-specific IP addresses or serial ports and must be reviewed before use.

## Safety boundary

This package is a software control layer. It does not replace an emergency stop, fusing, contactors, independent voltage/current monitoring, wiring review, DUT risk analysis, or hardware interlocks. The supplied source documentation identifies several SCPI details that still require verification on the exact instrument and firmware.

**Offline verification and RFDS-019 real-hardware keyword conformance are included as of v26.02. Full HIL qualification (Gates H1-H8) is not claimed.** Follow [Hardware qualification](guide/HARDWARE_QUALIFICATION.md) before production deployment.

## Project layout

```text
rf_ngi_n83624/            Robot Framework library package (library.py, evidence.py)
ngi_n83624/               inherited typed Python core driver
examples/                  14 Robot Framework examples
scripts/                   setup, test, build, example, and evidence-validation runners
tests/                     Python unit tests, Robot acceptance tests, RFDS-008 evidence tests
tests/hardware/            RFDS-019 real-hardware keyword conformance suite
schemas/evidence/          JSON Schemas for the RFDS-008 evidence artifacts
task/                      hardened generation/implementation task and readiness review
history/                   revision history
review/                    implementation code review and verification evidence
guide/                     PyCharm, Robot Framework, safety, HIL, and evidence guides
docs/                      GitHub Pages / MkDocs content
.github/workflows/         CI and Pages workflows
reference/                 supplied Python-driver task and documentation
```

## Release documentation

- [Final task specification](task/ROBOT_FRAMEWORK_DRIVER_TASK_v26.01.md)
- [Task readiness review](task/TASK_READINESS_REVIEW.md)
- [Implementation review](review/IMPLEMENTATION_REVIEW_v26.01.md)
- [Major fixes](review/MAJOR_FIXES_v26.01.md)
- [PyCharm and Robot Framework setup](guide/PYCHARM_ROBOT_FRAMEWORK_SETUP.md)
- [Hardware qualification](guide/HARDWARE_QUALIFICATION.md)
- [Evidence and diagnostics](guide/EVIDENCE_AND_DIAGNOSTICS.md)
- [Release history](history/v26.01.md), [v26.02](history/v26.02.md)
