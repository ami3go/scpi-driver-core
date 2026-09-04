# RF Agilent33220A

Robot Framework driver for the Agilent (Keysight) 33220A function/arbitrary
waveform generator. Version **26.2**. Gate 2 (Core Implementation,
RFDS-020): connection, output configuration, pulse, all five modulation
modes, sweep with marker, burst, trigger, arbitrary waveform upload, setup
save/restore, and a raw SCPI escape hatch are all implemented and tested
against the bundled simulator. Gate 3 (Extended Features): calibration
(behind a dedicated two-tier guard) and GPIB/LAN interface configuration are
also implemented. Gate 4 (full docs/AI contract/CI) and Gate 5
(review/release) have not started yet — see `task/` for the driver
specification and readiness review that shaped this implementation.

## Install

From this repository root:

```console
python -m pip install -e "./rf_agilent33220a[dev]"
```

Add `pyvisa` (and `pyvisa-py` for a pure-Python VISA backend) to talk to
real hardware over GPIB, USB, or LAN — all three are reachable through one
VISA resource string on this instrument, so no per-interface extra is
needed:

```console
python -m pip install -e "./rf_agilent33220a[visa,visa-py]"
```

Run the offline acceptance suite against the bundled simulator — no
generator required:

```console
python -m robot --outputdir results rf_agilent33220a/tests/robot/acceptance.robot
```

## Robot Framework use

```robotframework
*** Settings ***
Library         rf_agilent33220a.Agilent33220ALibrary
Suite Setup     Connect    simulated=${TRUE}
Suite Teardown  Disconnect

*** Test Cases ***
Configure A One Kilohertz Sine Output
    Configure Output    SINusoid    1000    1.0    0.0    enable_output=${TRUE}
    ${settings}=    Get Output Settings
    Should Be Equal    ${settings}[function]    SIN
    Disable Output
```

Against real hardware, pass a VISA resource string instead of
`simulated=${TRUE}`:

```robotframework
Connect    resource=USB0::0x0957::0x0407::<serial>::INSTR
```

See `examples/` for five runnable suites (identify, configure output,
modulation/sweep/burst, setup and arbitrary waveform, calibration and
interface configuration) and `tests/robot/acceptance.robot` for the full
offline coverage.

## Keywords

- **Connection (RFDS-002):** `Connect`, `Disconnect`, `Is Connected`,
  `Get Connection State`, `Check Communication`, `Get Identity`,
  `Switch Generator`, `Get Active Generator`, `List Generator Connections`
- **Output configuration:** `Set/Get Function`, `Set/Get Frequency`,
  `Set/Get Amplitude`, `Set/Get Amplitude Unit`, `Set/Get Offset`,
  `Set/Get Output Load`, `Set/Get Output Polarity`,
  `Set/Get Square Duty Cycle`, `Set/Get Ramp Symmetry`, `Configure Output`,
  `Enable Output`, `Disable Output`, `Is Output Enabled`,
  `Get Output Settings`
- **Front panel / display:** `Lock/Unlock Front Panel`,
  `Is Front Panel Locked`, `Set/Clear Display Text`,
  `Enable/Disable Display`
- **Pulse and modulation:** `Configure Pulse`,
  `Configure/Enable/Disable Amplitude Modulation`,
  `Configure/Enable/Disable Frequency Modulation`,
  `Configure/Enable/Disable Phase Modulation`,
  `Configure/Enable/Disable Frequency Shift Keying`,
  `Configure/Enable/Disable Pulse Width Modulation`
- **Sweep, burst, trigger:** `Configure Frequency Sweep`,
  `Enable/Disable Sweep`, `Set/Get Sweep Marker Frequency`,
  `Enable/Disable Sweep Marker`, `Configure Burst`, `Enable/Disable Burst`,
  `Set Burst Gate Polarity`, `Set/Get Trigger Source`,
  `Set/Get Trigger Slope`, `Get Trigger Settings`, `Trigger Now`
- **Arbitrary waveform:** `Load Arbitrary Waveform`,
  `Copy Arbitrary Waveform To Nonvolatile`, `Select Arbitrary Waveform`,
  `List Arbitrary Waveforms`, `Delete Arbitrary Waveform`,
  `Delete All Arbitrary Waveforms`, `Get Arbitrary Waveform Attributes`
- **Setup save/restore:** `Save Setup`, `Restore Setup`,
  `Save Setup To Instrument Memory`, `Restore Setup From Instrument Memory`,
  `Restore Factory Setup`
- **Calibration (Gate 3, behind a dedicated guard — see Safety notes):**
  `Enable Calibration Mode` (requires the exact confirmation text
  `"ENABLE CALIBRATION"`), `Run Calibration`, `Unlock Calibration`,
  `Lock Calibration`, `Is Calibration Locked` (read-only, no guard needed),
  `Set Calibration Security Code`, `Set/Get Calibration Step`,
  `Set/Get Calibration Value`, `Get Calibration Count` (read-only),
  `Set/Get Calibration String`
- **GPIB/LAN interface configuration (Gate 3):** `Set/Get GPIB Address`,
  `Set/Get LAN Auto IP`, `Set/Get LAN IP Address`,
  `Get LAN Logical IP Address` (read-only), `Get LAN MAC Address`
  (read-only), `Set/Get LAN Media Sense Enabled`,
  `Set/Get LAN NetBIOS Enabled`, `Set/Get LAN Telnet Prompt`,
  `Set/Get LAN Telnet Welcome Message`
- **Raw SCPI escape hatch:** `Enable Raw SCPI` (requires the exact
  confirmation text `"ENABLE RAW SCPI"`), `Raw SCPI Query`, `Raw SCPI Write`
- **Diagnostics:** `Export Diagnostic Bundle` — zips the current RFDS-008
  evidence run (see "Logging and evidence" below) for troubleshooting

Multiple generators can be driven from one suite via the `alias` parameter
accepted by every non-connection keyword.

## Logging and evidence

Every keyword call is recorded as structured, correlated RFDS-008 evidence —
arguments, duration, result/failure, and every SCPI command/response sent
over the wire — written to `results/session/rf_agilent33220a/<run>/`
(override with `RFDS_EVIDENCE_ROOT`). On by default; pass
`evidence_enabled=${FALSE}` to the `Library` import to disable it, or call
`Export Diagnostic Bundle` to zip the current run for a bug report. See
`docs/logging_and_evidence.md` for the full evidence layout and
`guide/evidence_and_diagnostics.md` for a task-oriented "my test failed, now
what" walkthrough. Validate a run's integrity (hashes, JSONL sequencing) with:

```console
python scripts/validate_evidence.py results/session/rf_agilent33220a/<run>/
```

## Hardware tests

`tests/hardware/verify_all_keywords.robot` is the RFDS-019 real-hardware
conformance suite: one test case per public keyword (117 total), run against
a real 33220A unit. It is tagged `hardware` and does not run in CI:

```console
python -m robot --outputdir results -v RESOURCE:USB0::0x0957::0x0407::<serial>::INSTR \
    tests/hardware/verify_all_keywords.robot
```

Several gates protect real-hardware side effects and are OFF by default:
`ALLOW_OUTPUT_ON` (energizes the output), `ALLOW_CALIBRATION` (touches
calibration memory — additionally needs `CALIBRATION_SECURITY_CODE`, the
unit's actual vendor code, or calibration-write keywords stay skipped even
with the gate on), `ALLOW_LAN_WRITES` (GPIB/LAN identity keywords — read-only
otherwise), and `ALLOW_SETUP_WRITES` (instrument-memory setup slots and
`*RST`). Every keyword that mutates device-persistent state restores the
original value before its own test case ends where the instrument makes that
possible to read back; Suite Teardown disables output and disconnects either
way.

## Running the tests

```console
python -m pip install -e "./rf_agilent33220a[dev,visa,visa-py]"
python -m pytest rf_agilent33220a                                    # unit + evidence tests, no hardware
python -m robot --outputdir results rf_agilent33220a/tests/robot/     # offline acceptance, bundled simulator
python -m robot --outputdir results -v RESOURCE:<visa string> \
    rf_agilent33220a/tests/hardware/verify_all_keywords.robot         # real hardware, RFDS-019
```

## Safety-relevant behaviors

- `APPLy` silently enables the output as a documented instrument side
  effect. `Configure Output` restores whatever output-enabled state existed
  beforehand unless `enable_output=${TRUE}` is explicitly passed — no
  keyword in this driver turns the output on except `Enable Output` and an
  explicit `Configure Output` call.
- `Set Amplitude`/`Set Offset` validate `Vpp < 2 × (Vmax − |Voffset|)`
  before any device I/O and raise `Agilent33220ASafetyError` specifically.
- `Restore Setup From Instrument Memory` checks `MEMory:STATe:VALid?` first
  and raises a clear error for an empty/never-saved slot instead of letting
  the instrument decide what an undefined recall means.
- **Calibration is behind a dedicated, two-tier guard**, separate from and
  in addition to the raw-SCPI guard: `Enable Calibration Mode` requires the
  exact confirmation text `"ENABLE CALIBRATION"` before any
  calibration-affecting keyword will run, and unlocking calibration itself
  (`Unlock Calibration`) additionally requires the instrument's own
  vendor security code. This is deliberately a different confirmation
  phrase from `Enable Raw SCPI`'s `"ENABLE RAW SCPI"` so a script can't
  accidentally satisfy one guard while meaning the other. Read-only
  calibration queries (`Is Calibration Locked`, `Get Calibration Count`)
  don't require the guard.
- An `ai/ai_contract.yaml` (RFDS-017 machine-readable contract) has not been
  generated yet; that is Gate 4 work.
