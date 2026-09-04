# RF Agilent34411A

Robot Framework driver for the Agilent (Keysight) 34411A 6.5-digit digital multimeter.
Version **26.2**. Gate 2 (Core Implementation, RFDS-020): connection, all measurement
functions (dc/ac voltage, dc/ac current, 2-/4-wire resistance, frequency/period,
capacitance, temperature, continuity, diode), math (dB/dBm/statistics/limit test),
trigger/sample configuration, reading memory and non-volatile-memory data logging, and
instrument state storage (5 non-volatile `MEMory:STATe` slots) are all implemented and
tested against the bundled simulator. Gate 3 (Extended Features): calibration (behind a
dedicated two-tier guard) and LAN interface configuration are also implemented. Gate 4
work has started: an RFDS-019 real-hardware keyword conformance suite and an RFDS-008
structured evidence/logging system are both in place (see "Hardware tests" and "Logging
and evidence" below); the RFDS-017 AI contract and CI wiring have not started yet, and
Gate 5 (review/release) has not started — see `task/` for the driver specification and
readiness review that shaped this implementation.

## Install

From this repository root:

```console
python -m pip install -e "./rf_agilent34411a[dev]"
```

Add `pyvisa` (and `pyvisa-py` for a pure-Python VISA backend) to talk to real hardware
over GPIB, USB, or LAN — all three are standard on this instrument and reachable through
one VISA resource string, so no per-interface extra is needed:

```console
python -m pip install -e "./rf_agilent34411a[visa,visa-py]"
```

Run the offline acceptance suite against the bundled simulator — no meter required:

```console
python -m robot --outputdir results rf_agilent34411a/tests/robot/acceptance.robot
```

## Robot Framework use

```robotframework
*** Settings ***
Library         rf_agilent34411a.Agilent34411ALibrary
Suite Setup     Connect    simulated=${TRUE}
Suite Teardown  Disconnect

*** Test Cases ***
Measure A DC Voltage
    Set Function    VOLT
    Set Range    VOLT    10
    Set Integration Time NPLC    VOLT    10
    ${reading}=    Get Immediate Measurement
    Log    Reading: ${reading} V
```

Against real hardware, pass a VISA resource string instead of `simulated=${TRUE}`:

```robotframework
Connect    resource=USB0::0x0957::0x0618::<serial>::INSTR
```

## Keywords

- **Connection (RFDS-002):** `Connect`, `Disconnect`, `Is Connected`,
  `Get Connection State`, `Check Communication`, `Get Identity`, `Switch Multimeter`,
  `Get Active Multimeter`, `List Multimeter Connections`
- **Function selection and per-function configuration** (every keyword below takes a
  `function` argument, e.g. `VOLT`, `VOLT:AC`, `CURR`, `CURR:AC`, `RES`, `FRES`, `FREQ`,
  `PER`, `CAP`, `TEMP`): `Set/Get Function`, `Set/Get Range`, `Set/Get Auto Range`,
  `Set/Get Integration Time NPLC`, `Set/Get Integration Time Aperture`,
  `Set/Get Auto Zero`, `Set/Get Offset Compensation`, `Set/Get AC Filter Bandwidth`,
  `Set/Get Input Impedance Auto` (dc voltage only), `Set/Get Null`,
  `Set/Get Null Value`, `Get Measurement Settings`
- **Temperature:** `Set/Get Temperature Probe Type`, `Set/Get Temperature Units`
- **Taking a reading:** `Get Immediate Measurement`, `Get Reading` — both raise
  `Agilent34411AOverloadError` on the documented `±9.9E+37` overload sentinel
- **Math:** `Get Math Function`, `Is Math Enabled`, `Enable dB Measurement`,
  `Set dB Reference`, `Enable dBm Measurement`, `Set dBm Reference Resistance`,
  `Enable Statistics`, `Get Statistics`, `Clear Statistics`, `Enable Limit Test`,
  `Set Limits`, `Get Limits`, `Disable Math`
- **Trigger and sample:** `Set/Get Trigger Source`, `Set/Get Trigger Level`,
  `Set/Get Trigger Slope`, `Set/Get Trigger Count`, `Set Trigger Delay`,
  `Set Trigger Delay Auto`, `Get Trigger Settings`, `Set/Get Sample Count`,
  `Set Sample Source`, `Set Sample Timer Interval`, `Set Pre-Trigger Sample Count`,
  `Trigger Now` (requires `BUS` trigger source)
- **Reading memory and non-volatile-memory data logging:** `Get Latest Reading`,
  `Get Most Recent Reading`, `Get Reading Count`, `Drain Readings`,
  `Copy Readings To Non-Volatile Memory` (the confirmed remote-driven data-logging
  mechanism — see Safety notes), `Get Non-Volatile Reading Count`,
  `Get Non-Volatile Readings`, `Clear Non-Volatile Readings`,
  `Drain Non-Volatile Readings`
- **Instrument memory state storage:** `Save Setup To Instrument Memory`,
  `Restore Setup From Instrument Memory`, `Get Instrument Memory Catalog`,
  `Rename Instrument Memory Slot`, `Get Instrument Memory Slot Name`,
  `Delete Instrument Memory Slot`, `Delete All Instrument Memory Slots`,
  `Is Instrument Memory Slot Valid`, `Get Instrument Memory Slot Count`,
  `Set Power-On State Recall`, `Set Power-On State`
- **Front panel / system:** `Get Active Input Terminals` (read-only),
  `Set/Get Beeper Enabled`, `Set/Get Display Enabled`, `Set Display Text`,
  `Clear Display Text`
- **Calibration (Gate 3, behind a dedicated guard — see Safety notes):**
  `Enable Calibration Mode` (requires the exact confirmation text
  `"ENABLE CALIBRATION"`), `Unlock Calibration`, `Lock Calibration`,
  `Is Calibration Locked` (read-only, no guard needed),
  `Set Calibration Security Code`, `Run Full Calibration`, `Run ADC Calibration`,
  `Set/Get Calibration Line Frequency`,
  `Get Actual Calibration Line Frequency` (read-only), `Store Calibration`,
  `Get Calibration Count` (read-only), `Set/Get Calibration String`,
  `Set/Get Calibration Value`
- **LAN configuration (Gate 3):** `Set/Get LAN DHCP Enabled`, `Set/Get LAN IP Address`,
  `Set/Get LAN Subnet Mask`, `Set/Get LAN Gateway`, `Set/Get LAN DNS`,
  `Set/Get LAN Hostname`, `Set/Get LAN Domain`, `Set/Get LAN Auto IP`,
  `Set/Get LAN DDNS Enabled`, `Set/Get LAN Keepalive`,
  `Get LAN Logical IP Address` (read-only), `Get LAN MAC Address` (read-only),
  `Get LAN Connection Status` (read-only), `Get LAN Control Connection Status`
  (read-only), `Set/Get LAN Media Sense Enabled`, `Set/Get LAN NetBIOS Enabled`,
  `Set/Get LAN Telnet Prompt`, `Set/Get LAN Telnet Welcome Message`,
  `Clear LAN History`, `Get LAN History`
- **Raw SCPI escape hatch:** `Enable Raw SCPI` (requires the exact confirmation text
  `"ENABLE RAW SCPI"`), `Raw SCPI Query`, `Raw SCPI Write`
- **Diagnostics:** `Export Diagnostic Bundle` — zips the current RFDS-008 evidence run
  (see "Logging and evidence" below) for troubleshooting

Multiple multimeters can be driven from one suite via the `alias` parameter accepted by
every non-connection keyword.

## Safety-relevant behaviors

- Overload readings (`±9.9E+37`, the documented out-of-range sentinel on a
  manually-selected fixed range) are surfaced as a typed `Agilent34411AOverloadError`,
  never handed back as a plausible-looking number.
- 4-wire resistance and 4-wire temperature measurements are always auto-zero on — this
  instrument has no `ZERO:AUTO` command for those functions at all, so `Set Auto Zero`
  raises a typed validation error instead of silently accepting and ignoring the call.
- `CALCulate:FUNCtion NULL` is never sent — it's documented as deprecated
  34401A-compatibility-only on this instrument; per-function null uses
  `[SENSe:]<function>:NULL` instead.
- There is no dedicated "start data logging" remote command on this instrument. The
  confirmed mechanism is to trigger a batch of readings (`Set Sample Count` + a trigger),
  then `Copy Readings To Non-Volatile Memory` to persist them — this driver implements
  exactly that path rather than a front-panel-only feature with no remote equivalent.
- `Check Communication`/`Connect` verify the instrument reports native `"34411A"` SCPI
  language mode (`SYSTem:LANguage?`) and raise a typed `Agilent34411AConfigurationError`
  otherwise — a unit left in `34401A`/`34410A` emulation mode by a previous user would
  otherwise silently break most of this driver's command surface.
- **Calibration is behind a dedicated, two-tier guard**, separate from and in addition to
  the raw-SCPI guard: `Enable Calibration Mode` requires the exact confirmation text
  `"ENABLE CALIBRATION"` before any calibration-affecting keyword will run, and unlocking
  calibration itself (`Unlock Calibration`) additionally requires the instrument's own
  security code. This is deliberately a different confirmation phrase from
  `Enable Raw SCPI`'s `"ENABLE RAW SCPI"` so a script can't accidentally satisfy one guard
  while meaning the other. Read-only calibration queries (`Is Calibration Locked`,
  `Get Calibration Count`, `Get Actual Calibration Line Frequency`) don't require the
  guard. `Store Calibration` writes calibration constants to non-volatile memory — a
  consequential, hardware-affecting operation on real instruments.
- LAN configuration keywords (Gate 3) carry no special guard — they're ordinary
  device-configuration commands with no documented risk to calibration data or
  measurement accuracy.
- An `ai/ai_contract.yaml` (RFDS-017 machine-readable contract) has not been generated
  yet; that is remaining Gate 4 work. When it is, this repository's convention names it
  `agilent34411a_ai_contract.yaml`/`.lock`.

## Logging and evidence

Every keyword call is recorded as structured, correlated RFDS-008 evidence — arguments,
duration, result/failure, and the underlying SCPI commands/responses for the alias it
targeted — written to `results/session/rf_agilent34411a/<run>/` (override with the
`RFDS_EVIDENCE_ROOT` environment variable). On by default; pass
`evidence_enabled=${FALSE}` to the `Library` import to disable it, or call
`Export Diagnostic Bundle` to zip the current run for a bug report. See
`docs/logging_and_evidence.md` for the full evidence layout and
`guide/evidence_and_diagnostics.md` for a task-oriented "my test failed, now what"
walkthrough. Validate a run's integrity (hashes, JSONL sequencing) with:

```console
python scripts/validate_evidence.py results/session/rf_agilent34411a/<run>/
```

## Hardware tests

`tests/hardware/verify_all_keywords.robot` exercises every one of this library's public
keywords against a real 34411A unit and checks its response — one test case per keyword
(149 total). It is tagged `hardware` and does not run in CI; run it explicitly:

```console
python -m robot --outputdir results -v RESOURCE:<visa resource string> \
    tests/hardware/verify_all_keywords.robot
```

Calibration-mutating keywords are skipped unless `-v ALLOW_CALIBRATION:True` is passed
(calibration changes persist and affect measurement accuracy on every subsequent use of
the instrument), LAN-identity `Set` keywords are read-only unless `-v ALLOW_LAN_WRITES:True`
is passed, `Delete All Instrument Memory Slots` is skipped unless
`-v ALLOW_DELETE_ALL_MEMORY:True` is passed, and the instrument-memory-slot tests use
`TEST_MEMORY_SLOT` (default `4`) and refuse to overwrite it if already occupied unless
`-v ALLOW_MEMORY_OVERWRITE:True` is passed. Every keyword that mutates device-persistent
state restores the original value before its own test case ends.

## Running the tests

```console
python -m pip install -e ".[dev,visa,visa-py]"
python -m pytest                                                    # unit + evidence tests, simulator only
python -m robot --outputdir results tests/robot/acceptance.robot    # offline acceptance, simulator only
python -m robot --outputdir results -v RESOURCE:<visa resource> \
    tests/hardware/verify_all_keywords.robot                        # real hardware, see above
```
