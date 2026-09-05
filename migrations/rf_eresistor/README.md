# RF E-Resistor

Robot Framework library for the OpenBench/RP2040 + W5500 E-Resistor programmable resistor matrix. Release **26.03** wraps the bundled and reviewed Python driver `eresistor-driver 0.1.1` without changing its SCPI, calibration, solver, safety, or HTTP fallback logic.

## Capabilities

- Connect and identify the board over SCPI/TCP (default port 5025)
- Control eight 16-bit matrix channels by mask
- Open all outputs safely
- Download, cache, save, and load calibration
- Calculate and set the closest resistance
- Apply multiple channel values atomically
- Convert temperature tables into resistance settings
- Discover boards, inspect errors/status, use raw SCPI, watchdog and metrics
- Return Robot-friendly dictionaries for result assertions
- Provide a locked, machine-readable RFDS-017 AI driver contract covering every Robot keyword
- Record every keyword call as RFDS-008 structured evidence (arguments, duration,
  SCPI/HTTP protocol trace, errors) for troubleshooting — see "Logging and evidence" below
- Export a real-hardware RFDS-019 conformance suite covering all 42 public keywords

## Install

Python 3.10 or newer is required.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux:   source .venv/bin/activate
python -m pip install -e ".[test,yaml]"
```

## Minimal real-hardware test

```robot
*** Settings ***
Library      rf_eresistor.EResistorLibrary    host=192.168.0.55
Suite Setup     Connect To EResistor    all_off_on_connect=${True}
Suite Teardown  Disconnect From EResistor

*** Test Cases ***
Set Ten Kilohms On Channel One
    Download EResistor Calibration
    ${result}=    Set EResistor Resistance    1    10000
    Log    mask=${result}[mask], actual=${result}[calculated_ohm] ohm
```

Run it with `robot --outputdir results examples/02_set_resistance.robot`.

## Safety

`0000` opens a channel. Bit 0 maps to Q16 (the lowest-value branch), bit 15 to Q1. `1` activates a MOSFET branch. The library defaults to `ALL:OFF` when it disconnects and can also open every output immediately on connect. Network loss cannot guarantee physical safe state without firmware-side watchdog support.

Do not connect a DUT until you have run the read-only identity example and verified the channel/mask mapping on your hardware. Use `force=True` only when intentionally overriding simulation-channel locking; it does not bypass resistance or active-bit safety limits.

## Logging and evidence

Every keyword call is recorded as structured, correlated RFDS-008 evidence —
arguments, duration, result/failure, and the underlying SCPI/HTTP exchanges —
written to `results/session/rf_eresistor/<run>/` (override with the
`RFDS_EVIDENCE_ROOT` environment variable). On by default; pass
`evidence_enabled=${FALSE}` to the `Library` import to disable it, or call
`Export Diagnostic Bundle` to zip the current run for a bug report. This is a
deeper, correlated complement to the existing `AuditLogger` facility
(`audit_log_file=...`), not a replacement for it — see
`docs/logging_and_evidence.md` for the full evidence layout and how the two
relate, and `guide/evidence_and_diagnostics.md` for a task-oriented "my test
failed, now what" walkthrough. Validate a run's integrity (hashes, JSONL
sequencing) with:

```console
python scripts/validate_evidence.py results/session/rf_eresistor/<run>/
```

## Hardware tests

`tests/hardware/verify_all_keywords.robot` is the RFDS-019 real-hardware
conformance suite: one test case per public keyword (42 total), run against a
real E-Resistor board. It is tagged `hardware` and does not run in CI:

```console
python -m robot --outputdir results -v HOST:192.168.0.55 tests/hardware/verify_all_keywords.robot
```

Every channel stays at mask `0000` (open) for the whole suite unless
`-v ALLOW_ACTIVATE:True` is passed — setting a mask/resistance/temperature
activates a MOSFET branch and can drive current through whatever is wired to
that channel (see "Safety" above: verify the channel/mask mapping before
connecting a DUT). Discovery keywords additionally require
`-v ALLOW_DISCOVERY:True` (plus `-v DISCOVERY_SUBNET:<cidr>` for the
manual-subnet variant) since a network scan is disruptive/unexpected default
behavior. Test Teardown and Suite Teardown always attempt to reopen every
channel regardless of how a test case left the board.

## Documentation

- [Keyword reference](docs/keyword_reference.md)
- [Logging and evidence](docs/logging_and_evidence.md)
- [Evidence and diagnostics guide](guide/evidence_and_diagnostics.md)
- [Installation and PyCharm/Robot guide](guide/pycharm_robot_framework_setup.md)
- [Hardware setup](guide/hardware_setup.md)
- [Examples](examples/README.md)
- [Release history](history/v26.01.md)
- [Implementation review](review/v26.01_code_review.md)
- [AI driver contract](ai/README.md)
- [Release 26.02 history](history/v26.02.md)
- [Release 26.02 compliance review](review/v26.02_code_review.md)
- [Release 26.03 history](history/v26.03.md)

Generate Robot's HTML keyword documentation with:

```bash
python -m robot.libdoc rf_eresistor docs/rf_eresistor.html
```

The `docs/` folder is GitHub Pages ready. Enable Pages from the repository root or publish that folder with your preferred workflow.

## Running the tests

Unit tests (`tests/test_robot_adapter.py`, `tests/test_ai_contract.py`,
`tests/evidence/`) use hand-rolled fakes, so they need no E-Resistor hardware:

```bash
python -m pytest
python -m robot --outputdir results tests/robot
```

Hardware examples and `tests/hardware/verify_all_keywords.robot` are
deliberately not part of the offline test suite — see "Hardware tests" above
for how to run the real-hardware conformance suite.
