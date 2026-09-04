# RF TBS1000C

Robot Framework driver for the Tektronix TBS1000C digital storage
oscilloscope. Version **26.02**. Gate 2 (Core Implementation, RFDS-020):
connection, channel/trigger/acquisition configuration, calibration,
measurements, waveform fetch, screen/CSV/setup save-restore, and a raw SCPI
escape hatch are all implemented and tested against the bundled simulator.
Gate 3 (Extended Features): instrument-side waveform save/recall via
reference memory is also implemented. Gate 4 (full docs/AI contract/CI) and
Gate 5 (review/release) have not started yet — see `task/` for the driver
specification and readiness review that shaped this implementation.

## Install

From this repository root:

```console
python -m pip install -e "./rf_tbs1000c[dev]"
```

Add `pyvisa` to talk to real hardware over USBTMC:

```console
python -m pip install -e "./rf_tbs1000c[usbtmc]"
```

Run the offline acceptance suite against the bundled simulator — no scope
required:

```console
python -m robot --outputdir results rf_tbs1000c/tests/robot/acceptance.robot
```

## Robot Framework use

```robotframework
*** Settings ***
Library         rf_tbs1000c.Tbs1000cLibrary
Suite Setup     Connect    simulated=${TRUE}
Suite Teardown  Disconnect

*** Test Cases ***
Measure Channel One Frequency
    Set Channel Scale    1    0.5
    Set Trigger Source    1
    Auto Set Trigger Level
    ${frequency}=    Get Immediate Measurement    FREQuency    1
    Measurement Should Be Within    FREQuency    1    1.0    1.0E6
```

Against real hardware, pass a VISA resource string instead of
`simulated=${TRUE}`:

```robotframework
Connect    resource=USB0::0x0699::0x03C4::<serial>::INSTR
```

See `examples/` for three runnable suites (identify, configure-and-measure,
waveform-and-evidence) and `tests/robot/acceptance.robot` for the full
offline coverage.

## Keywords

- **Connection (RFDS-002):** `Connect`, `Disconnect`, `Is Connected`,
  `Get Connection State`, `Check Communication`, `Get Identity`,
  `Switch Oscilloscope`, `Get Active Oscilloscope`,
  `List Oscilloscope Connections`
- **Channel setup:** `Set/Get Channel Scale`, `Set/Get Channel Position`,
  `Set/Get Channel Offset`, `Set/Get Channel Coupling`,
  `Set/Get Channel Bandwidth Limit`, `Set/Get Channel Probe Gain`,
  `Set/Get Channel Name`, `Get Channel Settings`
- **Trigger:** `Set/Get Trigger Source`, `Set/Get Trigger Slope`,
  `Set/Get Trigger Coupling`, `Set/Get Trigger Level`,
  `Auto Set Trigger Level`, `Force Trigger`, `Get Trigger Settings`
- **Acquisition:** `Run Autoset`, `Start Acquisition`, `Stop Acquisition`,
  `Set/Get Acquisition Mode`, `Get Acquisition Count`
- **Calibration:** `Run Internal Calibration`, `Get Calibration Status`,
  `Get Calibration Results` — never run implicitly by any other keyword
- **Measurement and waveform:** `Get Immediate Measurement`,
  `Measurement Should Be Within`, `Get Waveform`, `Save Screen Image`,
  `Save Waveform To CSV`, `Save Waveform To CSV On Instrument`,
  `Save Waveform To Reference Memory` (instrument-side, no host file
  transfer), `Recall Waveform From Host File` (uploads a host file and
  loads it into reference memory — Gate 3)
- **Setup save/restore:** `Save Setup`, `Restore Setup`,
  `Save Setup To Instrument Memory`, `Restore Setup From Instrument Memory`,
  `Restore Factory Setup`
- **Raw SCPI escape hatch:** `Enable Raw SCPI` (requires the exact
  confirmation text `"ENABLE RAW SCPI"`), `Raw SCPI Query`, `Raw SCPI Write`
- **RFDS-008 evidence:** `Export Diagnostic Bundle` — zips the current
  session's structured evidence run for troubleshooting (see "Logging and
  evidence" below)

Multiple oscilloscopes can be driven from one suite via the `alias`
parameter accepted by every non-connection keyword.

## Notes

- `Restore Setup` verifies the resent `*LRN?` string via the instrument's
  error queue rather than assuming success.
- Waveform decoding trusts only the declared IEEE-488.2 binary-block length —
  it never strips the raw sample bytes, since a legitimate sample value can
  equal a whitespace byte.
- An `ai/ai_contract.yaml` (RFDS-017 machine-readable contract) has not been
  generated yet; that is Gate 4 work.

## Logging and evidence

Every keyword call is recorded as structured, correlated RFDS-008 evidence —
arguments, duration, result/failure, and the literal SCPI commands/responses
exchanged with the instrument (via a transparent `InstrumentedTransport`
wrapper around each session's transport) — written to
`results/session/rf_tbs1000c/<run>/` (override with `RFDS_EVIDENCE_ROOT`).
On by default; pass `evidence_enabled=${FALSE}` to the `Library` import to
disable it, or call `Export Diagnostic Bundle` to zip the current run for a
bug report. The run is finalized when the suite ends (this driver already
implements a Robot listener hook, `_end_suite`, for session cleanup; evidence
finalization now happens there too). See `docs/logging_and_evidence.md` for
the full evidence layout and `guide/evidence_and_diagnostics.md` for a
task-oriented "my test failed, now what" walkthrough. Validate a run's
integrity (hashes, JSONL sequencing) with:

```console
python scripts/validate_evidence.py results/session/rf_tbs1000c/<run>/
```

## Hardware tests

`tests/hardware/verify_all_keywords.robot` exercises every one of this
library's 60 public keywords (plus `Export Diagnostic Bundle`) against a
real TBS1000C — one test case per keyword. It is tagged `hardware` and does
not run in CI; run it explicitly with a real VISA USBTMC resource string:

```console
python -m robot --outputdir results \
    -v RESOURCE:USB0::0x0699::0x03C4::<serial>::INSTR \
    tests/hardware/verify_all_keywords.robot
```

Channel/trigger/acquisition settings are captured at Suite Setup and restored
at Suite Teardown regardless of which keywords ran or failed. Three flags
gate operations that are disruptive or touch instrument-persistent storage —
see the suite's own `Documentation` for exactly what each unlocks:
`ALLOW_CALIBRATION` (`Run Internal Calibration` takes the instrument offline
for the duration), `ALLOW_FACTORY_RESET` (`Restore Factory Setup` wipes all
current settings — the suite restores the pre-test setup immediately
afterward), and `ALLOW_INSTRUMENT_MEMORY_WRITE` (any keyword writing to a
setup/reference-waveform memory slot or the instrument's own filesystem,
using a scratch slot identified by `SCRATCH_SLOT` — verify that slot is
unused on your bench first).

## Running the tests

```console
python -m pip install -e ".[dev]"          # unit + evidence tests, no hardware needed
python -m pytest
python -m robot --outputdir results rf_tbs1000c/tests/robot/acceptance.robot   # simulator-backed
```

`tests/hardware/verify_all_keywords.robot` (above) needs real hardware.
`tests/unit/` and `tests/evidence/` use the bundled simulator or an
injectable test double and need no hardware or vendor SDK at all.
