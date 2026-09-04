# Robot Framework Driver Task: Agilent 34411A 6½-Digit Digital Multimeter

**Status:** Gate 1 — Architecture & Skeleton task document (RFDS-020). No code has been
written yet. This document is the pre-code planning artifact; see
`rf_tbs1000c/task/` and `rf_agilent33220a/task/` in this repository for the two prior
task documents this one follows in structure.

## 1. Objective

Implement `rf_agilent34411a`, a Robot Framework driver for the Agilent (later Keysight)
34411A 6½-digit digital multimeter, following this repository's two-layer architecture
(hardware-agnostic core driver + thin Robot Framework adapter) and RFDS-001 through
RFDS-020.

The 34411A is a bench DMM: dc/ac voltage and current, 2-wire/4-wire resistance,
frequency/period, capacitance, temperature (RTD/thermistor), continuity, and diode test,
with GPIB/USB/LAN standard on every unit, non-volatile reading memory (data logging),
5 stored instrument states, and — unique to the 34411A/L4411A relative to the base
34410A — up to 50,000 readings/second, a 1-million-reading buffer, internal (level)
triggering, and pre-triggering. This task explicitly scopes the driver to the 34411A;
where the SCPI surface is shared verbatim with the 34410A (nearly all of it), that is
noted, and 34411A-only extensions are called out explicitly per RFDS-005.

## 2. Instrument facts (sources: Agilent 34410A/11A/L4411A User's Guide, part number
34410-90001, Fourth Edition, February 2007; and Agilent 34410A/11A Command Quick
Reference, Agilent Technologies, January 2006 — a condensed but complete syntax listing
of every SCPI command this instrument family supports, which resolved every command-
syntax open question the User's Guide alone left unconfirmed. Both were read directly
during Gate 1 research; nothing in this section is inferred or guessed.)

- **Remote interfaces:** GPIB (IEEE-488), USB, and LAN are all standard and enabled at
  power-on — one VISA transport is sufficient, matching the precedent set by
  `rf_agilent33220a` (no per-interface backends needed). LXI Class C compliant, with a
  built-in web interface for configuration and reading retrieval (not in scope for this
  driver; SCPI only, per RFDS-005's "no vendor GUI dependency" rule).
- **SCPI command surface (per §2 "Features and Functions" of the User's Guide,
  cross-referenced against the *Programmer's Reference Help*, which is the normative
  syntax source but was not directly available for this task — every command cited here
  was independently confirmed in the User's Guide's own "Remote Interface Operation"
  examples, so no command in this document is a guess):
  - **Common/standard commands:** `*IDN?`, `*CLS`, `*RST`, `*TST?`, `SYSTem:PRESet`.
  - **Per-function `[SENSe:]` subsystem** — the primary configuration path documented
    throughout the manual (not the `CONFigure`/`MEASure` convenience family, which the
    manual mentions only as syntactic sugar that also resets the trigger source to
    `IMMediate`):
    - `[SENSe:]VOLTage[:DC]:NPLC {<PLCs>|MIN|MAX|DEF}`, `:APERture {<seconds>|MIN|MAX|DEF}`,
      `:RANGe[:UPPER] {<range>|MIN|MAX|DEF}`, `:RANGe:AUTO {OFF|ONCE|ON}`,
      `:IMPedance:AUTO {OFF|ON}` (Hi-Z >10 GΩ vs fixed 10 MΩ, 100 mVdc/1 Vdc/10 Vdc
      ranges only), `:ZERO:AUTO {OFF|ONCE|ON}`, `:NULL[:STATe] {ON|OFF}`,
      `:NULL[:VALue] {<value>|MIN|MAX}`.
    - `[SENSe:]CURRent[:DC]:...` — same sub-command family as `VOLTage[:DC]`.
    - `[SENSe:]VOLTage:AC:BANDwidth {<filter>|MIN|MAX|DEF}` (3/20/200 Hz),
      `:RANGe...`, `:NULL...`. `[SENSe:]CURRent:AC:...` mirrors it.
    - `[SENSe:]RESistance:...` (2-wire), `[SENSe:]FRESistance:...` (4-wire) — both
      support `:NPLC`, `:APERture`, `:RANGe`, `:RANGe:AUTO`, `:OCOMpensated {ON|OFF}`
      (offset compensation), `:ZERO:AUTO`, `:NULL...`.
    - `[SENSe:]FREQuency:APERture {<seconds>|MIN|MAX|DEF}`,
      `[SENSe:]PERiod:APERture {...}`, both with `:RANGe`/`:RANGe:AUTO` acting on the
      *ac voltage input level* (there is no separate frequency amplitude range), plus
      shared `VOLTage:AC:BANDwidth` and `:NULL`.
    - `[SENSe:]CAPacitance:RANGe...`, `:RANGe:AUTO`, `:NULL...` (no integration/NPLC —
      capacitance uses a fixed charge/discharge measurement method, not ADC
      integration).
    - `[SENSe:]TEMPerature:...` — `:TRANsducer:TYPE {RTD|THERmistor}`,
      `:TRANsducer:RTD:TYPE {85 (0.00385%/°C)}`, `:TRANsducer:THERmistor:TYPE
      {2252|5000|10000}` (2.2 kΩ/5 kΩ/10 kΩ), plus `:NPLC`, `:APERture`,
      `:OCOMpensated` (RTD only), `:ZERO:AUTO` (2-wire only; 4-wire is always
      auto-zero on per the manual), `:NULL...`, and a units selector,
      `UNIT:TEMPerature {C|F|K}` — confirmed exactly against the Command Quick
      Reference (this was previously an open question; it is resolved).
    - Continuity and diode test have **no configurable parameters** — fixed 1 kΩ range
      (continuity, 10 Ω beep threshold, "OPEN" above 1.2 kΩ) and fixed 1 Vdc/1 mA range
      (diode, 0.3–0.8 V beep threshold, "OPEN" above 1.2 V) respectively.
  - **Function selection / readback:** `[SENSe:]FUNCtion "<function>"` (quoted string
    form is the SCPI norm for this family; confirmed via the manual's function-name
    vocabulary — `"VOLT"`, `"VOLT:AC"`, `"CURR"`, `"CURR:AC"`, `"RES"`, `"FRES"`,
    `"FREQ"`, `"PER"`, `"CAP"`, `"TEMP"`, `"CONT"`, `"DIOD"`).
  - **Triggering (`TRIGger:` and `SAMPle:` subsystems):**
    `TRIGger:SOURce {IMMediate|EXTernal|BUS|INTernal}` — `INTernal` (level triggering)
    is **34411A/L4411A only**; `TRIGger:LEVel <level>` and `TRIGger:SLOPe {POS|NEG}` set
    the internal-trigger level/edge (34411A/L4411A only, ac/dc voltage, ac/dc current,
    2-wire/4-wire resistance only). `TRIGger:COUNt {<count>|MIN|MAX|DEF|INFinity}`
    (number of *trigger events* accepted — distinct from `SAMPle:COUNt`, the number of
    *samples per trigger*; total readings = trigger count × sample count, the standard
    SCPI trigger model, confirmed via the Command Quick Reference and previously
    missing from this document's §9 keyword list), `TRIGger:DELay
    {<seconds>|MIN|MAX}`, `TRIGger:DELay:AUTO`, `SAMPle:COUNt {<count>|MIN|MAX|
    INFinity}`, `SAMPle:COUNt:PRETrigger {<count>|MIN|MAX}` (**34411A/L4411A only**;
    pre-trigger count must be less than sample count), `SAMPle:SOURce {AUTO|TIMer}`,
    `SAMPle:TIMer {<interval>|MIN|MAX}` (fixed inter-sample interval when
    `SAMPle:SOURce TIMer` — also confirmed via the Command Quick Reference and
    previously missing from §9). `INITiate[:IMMediate]`, `ABORt`, `READ?`, `FETCh?`,
    `MEASure?` (family — `MEASure?` and `CONFigure` both force `TRIGger:SOURce
    IMMediate`, per the User's Guide).
  - **Math (`CALCulate:` subsystem)** — distinct from the per-function `NULL` above,
    and only one math function active at a time: `CALCulate:FUNCtion
    {DB|DBM|AVERage|LIMit}` (the family also lists `NULL`, but the manual explicitly
    flags that value as deprecated SCPI-compatibility-only for the older 34401A — this
    driver must use the per-function `[SENSe:]<func>:NULL` path, never
    `CALCulate:FUNCtion NULL`), `CALCulate:STATe {ON|OFF}`,
    `CALCulate:DB:REFerence <value>`, `CALCulate:DBM:REFerence <value>` (ac/dc voltage
    only; resistance values 50/75/93/110/124/125/135/150/250/300/500/600/800/900/1000/
    1200/8000 Ω, default 600 Ω), `CALCulate:AVERage:AVERage?`/`:MINimum?`/`:MAXimum?`/
    `:SDEViation?`/`:PTPeak?`/`:COUNt?` (statistics), `CALCulate:AVERage:CLEar`,
    `CALCulate:LIMit:LOWer <value>`, `:UPPer <value>`, both queryable.
  - **Reading memory, confirmed in full against the Command Quick Reference** (this
    resolves the previous "`FETCh?` semantics are ambiguous" note, and previous open
    question §19 item 2 — no separate remote "start logging" command exists; remote
    data logging is done by taking many samples and persisting them):
    - `FETCh?` — retrieve the reading(s) triggered by the most recent `INITiate`/
      `READ?`/`MEASure?`, from the instrument's internal (volatile) reading memory,
      without erasing them.
    - `DATA:LAST?` — the single most recent reading.
    - `DATA:POINts?` — count of readings currently in volatile reading memory.
    - `DATA:POINts:EVENt:THReshold <num_readings>` / `?` — a threshold used with the
      status system to signal when enough readings have accumulated (relevant to
      building a polling-free "wait for N readings" keyword; not required for Gate 2).
    - `DATA:REMove? <num_readings>` — pop and return the oldest N readings from
      volatile memory (destructive read, FIFO order).
    - `DATA:COPY NVMEM, RDG_STORE` — **the actual remote-driven "data logging"
      mechanism**: copies the current contents of volatile reading memory into
      non-volatile memory (`RDG_STORE` is the fixed non-volatile-memory reading-store
      name this command addresses). This is how a Robot suite persists a batch of
      triggered readings without needing the front-panel Data Logger wizard at all —
      configure `SAMPle:COUNt`, trigger, then `DATA:COPY NVMEM, RDG_STORE`.
    - `DATA:DATA? NVMEM` — return all readings currently in non-volatile memory.
    - `DATA:DELete NVMEM` — clear non-volatile memory.
    - `R? [<max_count>]` — pop and return up to `<max_count>` readings from
      non-volatile memory (destructive read).
    - Capacity: **1 million readings** (volatile+non-volatile combined capacity context)
      on the 34411A/L4411A (vs. 50,000 on the base 34410A).
  - **Instrument state storage (`MEMory:` subsystem, non-volatile), confirmed in full
    against the Command Quick Reference** (this resolves previous open question §19
    item 3 — the guessed `*SAV`/`*RCL`-with-slot-number shape was correct, and the
    `MEMory:STATe:*` family is fully enumerated below, none of it guessed):
    - `*SAV {0|1|2|3|4}` / `*RCL {0|1|2|3|4}` — save/recall the 5 non-volatile states
      (state 0 is the power-down-recall state; 1–4 are general-purpose).
    - `MEMory:NSTates?` — number of available state slots (5).
    - `MEMory:STATe:CATalog?` — list of in-use states.
    - `MEMory:STATe:DELete {0|1|2|3|4}` / `:DELete:ALL`.
    - `MEMory:STATe:NAME {0|1|2|3|4} [,<name>]` / `:NAME? {0|1|2|3|4}` — up to
      12-character names, per the User's Guide.
    - `MEMory:STATe:RECall:AUTO {OFF|0|ON|1}` / `:RECall:AUTO?` — whether a stored
      state (rather than factory defaults) is recalled at power-on.
    - `MEMory:STATe:RECall:SELect {0|1|2|3|4}` / `:RECall:SELect?` — which stored
      state is recalled at power-on when `RECall:AUTO` is on.
    - `MEMory:STATe:VALid? {0|1|2|3|4}` — whether a given slot has ever been saved to;
      the same "check validity before recalling" pattern already implemented for
      `rf_agilent33220a`'s `restore_setup_from_instrument_memory` (task §11 there) — a
      recall of an unsaved slot should be rejected client-side with a typed error
      before sending `*RCL`, exactly as done there, rather than sending `*RCL` and
      letting the instrument decide what an undefined recall means.
    - No `*LRN?`-equivalent host-file save/restore command was found in either source —
      this instrument's state persistence is entirely instrument-resident via
      `MEMory:`/`*SAV`/`*RCL`. A host-file `Save Setup`/`Restore Setup` pair (as
      implemented for `rf_agilent33220a`/`rf_tbs1000c`) remains **out of scope** for
      this driver; §11's plan (instrument-memory-only state storage) is confirmed
      correct as originally written, not merely deferred.
  - **System/utility, with additions confirmed against the Command Quick Reference:**
    `SYSTem:ERRor[:NEXT]?` (FIFO, up to 20 entries, per-interface + a global queue,
    `*CLS` and power-cycle clear it, `SYSTem:PRESet`/`*RST` do not),
    `SYSTem:BEEPer:STATe {OFF|ON}`, `SYSTem:BEEPer[:IMMediate]` (bare — always beeps
    once regardless of beeper state, used as an audible "done" signal),
    `SYSTem:COMMunicate:ENABle {OFF|ON},{GPIB|USB|LAN|SOCKets|TELNet|VXI11|WEB}` and the
    matching query, `SYSTem:COMMunicate:GPIB[:SELF]:ADDRess {<address>}` and query,
    `DISPlay[:WINDow[1|2]][:STATe] {OFF|ON}` and query,
    `DISPlay[:WINDow[{1|2}]]:TEXT:CLEar`,
    `DISPlay[:WINDow[{1|2}]]:TEXT[:DATA] "<string>"` and query,
    `DISPlay:WINDow2:TEXT:FEED "<feed>"` (second-display-line source selector) and
    query, `ROUTe:TERMinals?` (front/rear switch readback — **not settable remotely**;
    the hardware switch is the only way to change it, so this driver must never attempt
    to write it), `*TST?` (returns `+0` pass / `+1` fail),
    `FORMat[:DATA] {ASCii|REAL} [,<length>]` and query (binary vs. ASCII reading
    transfer format — this driver stays ASCII-only for Gate 2, matching every other
    text-only transport decision already made in this repository for instruments whose
    protocol doesn't require binary transfer for correctness).
  - **`SYSTem:LANguage` caution (new finding, not previously documented in this task):**
    the instrument supports a SCPI-dialect emulation mode,
    `SYSTem:LANguage "{34401A|34410A|34411A}"`, letting it emulate an older 34401A's or
    34410A's command set instead of its own native 34411A dialect. This driver must
    **never write** `SYSTem:LANguage` and should treat a non-`"34411A"` value as a
    connection-time configuration error (surfaced via `Check Communication`/`Connect`),
    since every command in this task document assumes native 34411A language mode — a
    unit left in `34401A` or `34410A` emulation mode by a previous user/script would
    silently break large parts of this driver's command surface.
  - **Overload indication:** out-of-range readings on a manually-selected fixed range
    return `±9.9E+37` over the remote interface (`±OVLD` on the front panel). The driver
    must surface this as a typed, named condition rather than a plausible-looking float
    (mirrors the general instrument-contract principle already applied to
    `rf_agilent33220a`'s settings-conflict and safety-limit handling).
  - **Calibration:** front-panel/service-only, secured with a factory code; the manual
    explicitly says only service-qualified personnel should calibrate the instrument
    and defers to the *Service Guide*. No calibration keywords are in scope for this
    driver (matches the precedent already set for `rf_agilent33220a`, which also
    excludes calibration commands from its typed keyword surface).
- **Ranges (from the DC Characteristics accuracy table, §5 "Specifications"):**
  - DC voltage: 100.0000 mV, 1.000000 V, 10.00000 V, 100.0000 V, 1000.000 V.
  - Resistance (2-wire and 4-wire): 100.0000 Ω, 1.000000 kΩ, 10.00000 kΩ, 100.0000 kΩ,
    1.000000 MΩ, 10.00000 MΩ, 100.0000 MΩ, 1000.000 MΩ (the top two ranges are
    implemented as 10 MΩ in parallel with a shunt and require Math Null for rated
    accuracy, per table footnote 4).
  - DC current: 100.0000 µA, 1.000000 mA, 10.00000 mA, 100.0000 mA, 1.000000 A,
    3.00000 A (a separately fused current input terminal, 3 A rms Protection Limit).
  - Capacitance: 5 ranges, 1 nF to 10 µF, each range decade-spaced (1 nF, 10 nF,
    100 nF, 1 µF, 10 µF); accuracy 0.4% reading + 0.1% range (0.5%+0.5% on the 1 nF
    range).
  - Continuity: fixed 1 kΩ range. Diode: fixed 1 Vdc range, 1 mA source.
  - AC voltage/current and frequency/period ranges were not transcribed in this task
    document (not read from the source manual during Gate 1 research) and must be
    pulled from §5 "AC Characteristics"/"Frequency and Period Characteristics" before
    Gate 2 configuration-keyword implementation — see §19 item 4.
- **Integration time:** NPLC values are `{0.001, 0.002, 0.006, 0.02, 0.06, 0.2, 1, 2,
  10, 100}` on the 34411A/L4411A (the base 34410A lacks 0.001 and 0.002). Aperture mode
  (seconds, not tied to line frequency) ranges **20 µs to 1 s** on the 34411A/L4411A
  (100 µs to 1 s on the 34410A) — this driver targets the wider 34411A range. Default
  is 1 PLC.
- **Front/rear input terminal switch:** a physical, front-panel-only switch selecting
  which terminal set (front or rear) is internally connected; `ROUTe:TERMinals?` reads
  it back but there is no remote-settable equivalent, and the manual carries an explicit
  **WARNING**: do not change the switch position while signals are present on either
  terminal set — may cause instrument damage or electric shock. This driver must
  document that warning verbatim in the connection-keyword docstring and must never
  attempt to write `ROUTe:TERMinals`.
- **Protection limits (safety-relevant, task §6):** HI-to-LO 1000 VDC / 750 VAC (also
  the max voltage measurement, 1000 Vpk); LO-to-ground 500 Vpk; current terminal 3 A
  rms, separately fused; sense-terminal pairs (4-wire) 200 Vpk. IEC Measurement
  Category II up to 300 VAC on the mains-connectable HI/LO inputs. These are physical
  hardware limits, not software-enforceable — this driver documents them but does not
  (and cannot) enforce them in software; unlike `rf_agilent33220a`'s amplitude/offset
  check, there is no analogous pre-write SCPI validation to perform here because the
  DMM is a passive measurement instrument, not a source.

## 3. Mandatory package structure

Mirrors `rf_agilent33220a` and `rf_tbs1000c` (RFDS-005):

```
rf_agilent34411a/
├── LICENSE
├── pyproject.toml
├── README.md
├── task/
│   └── ROBOT_FRAMEWORK_DRIVER_TASK_v26.01.md   (this file)
├── agilent34411a/            # hardware-agnostic core driver
│   ├── __init__.py
│   ├── exceptions.py
│   ├── enums.py
│   ├── models.py
│   ├── transport.py
│   ├── simulator.py
│   └── driver.py
├── rf_agilent34411a/         # Robot Framework adapter
│   ├── __init__.py
│   └── library.py
├── tests/
│   ├── unit/
│   └── robot/
└── examples/
```

## 4. Versioning and packaging

- Python distribution name: `robotframework-agilent34411a`.
- Version: `26.1` (matches the `rf_agilent33220a`/`rf_tbs1000c` Gate 2 baseline
  convention in this repository — first release cut this calendar cycle).
- `pyproject.toml` optional dependencies: `visa` (`pyvisa>=1.14`), `visa-py`
  (`pyvisa-py>=0.7`, pure-Python VISA backend), `dev` (`pytest`, `pytest-cov`, `ruff`,
  `mypy`, `build`) — identical shape to `rf_agilent33220a/pyproject.toml`, since both
  instruments use a single standard VISA transport.
- `requires-python = ">=3.10"`, `robotframework>=7.0,<9"` core dependency, MIT license.

## 5. Architecture

Two layers, per RFDS-003/RFDS-004:

- **`agilent34411a`** — hardware-agnostic core. Owns all SCPI command construction and
  response parsing; the Robot adapter must not duplicate any of this logic (same rule
  already applied in `rf_agilent33220a`/`rf_tbs1000c`).
  - `transport.py`: a `Transport` Protocol, `PyvisaTransport` (lazy `pyvisa` import so
    the package stays importable without the VISA extra installed), and
    `SimulatedTransport` wrapping an in-process `SimAgilent34411AInstrument`. One
    transport class covers GPIB/USB/LAN, exactly as `rf_agilent33220a` established for
    its own single-VISA-backend instrument (task §5.1 there) — the same reasoning
    applies here since all three interfaces are standard and equally reachable through
    one VISA resource string.
  - `enums.py`: `_ScpiEnum(str, Enum)` base with the same generic case-insensitive
    prefix-matching `_missing_` hook already proven in `rf_agilent33220a` (SCPI's
    canonical short mnemonic is always a prefix of its long form) — reuse that exact
    pattern rather than re-deriving it. Concrete enums: `Function`, `AcFilter`
    (`SLOW`/`MEDium`/`FAST`), `TriggerSource`, `TriggerSlope`, `TemperatureProbeType`,
    `TemperatureUnit`, `AutoZeroMode` (`OFF`/`ONCE`/`ON` — a 3-state enum, distinct from
    a plain bool, since `ONCE` is a real, meaningfully different mode used throughout
    this instrument), `MathFunction`.
  - `models.py`: `InstrumentIdentity`, `MeasurementSettings` (per-function config
    snapshot), `TriggerSettings`, `StatisticsResult`, `ConnectionState` (RFDS-002 §12.1
    shape, `as_dict()` — same as `rf_agilent33220a`'s `models.ConnectionState`).
  - `simulator.py`: `SimAgilent34411AInstrument`, dict-based `_ROUTES` dispatcher (same
    proven pattern as `rf_agilent33220a`/`rf_tbs1000c`), plus the `;`/`:`
    concatenated-command replay method (`_dispatch_concatenated`) needed for state
    save/restore, ported and adapted from `rf_agilent33220a`'s
    `SimAgilent33220AInstrument._dispatch_concatenated` (including its `explicit_root`
    fix for bare single-word segments inheriting the wrong command group — that bug
    class applies here too, since this instrument's state-restore mechanism will use
    the same `;`-separated replay shape).
  - `driver.py`: `Agilent34411A` class — connection lifecycle, per-function measurement
    configuration, math, trigger/sample, reading-memory access, data logging, state
    storage, raw SCPI escape hatch.
- **`rf_agilent34411a`** — Robot Framework adapter (`Agilent34411ALibrary`). RFDS-002
  canonical keywords as the primary API, multi-alias session management (`_sessions`
  dict, `_active_alias`, `_session(alias)` resolver — same shape as
  `rf_agilent33220a.library.Agilent33220ALibrary`), a `_connection_state(alias, driver)`
  helper, and a `_robot_value()` dataclass/enum-to-dict converter (identical
  implementation to the one already proven in `rf_tbs1000c`/`rf_agilent33220a` —
  reuse the pattern verbatim, no redesign needed).

## 6. Signal-integrity and safety requirements

1. **Front/rear switch is read-only from software.** `Get Active Input Terminals`
   (wrapping `ROUTe:TERMinals?`) is the only terminal-switch keyword; there is no
   `Set Active Input Terminals` keyword, and the docstring must carry the manual's
   verbatim warning about not switching under load.
2. **Calibration is out of scope.** No calibration keyword is exposed, matching
   `rf_agilent33220a`'s precedent of excluding service-only, factory-secured
   functionality from the typed keyword surface.
3. **Overload is a typed condition, not a silently-passed sentinel float.** Any
   keyword that returns a measurement (`Get Immediate Measurement`,
   `Get Reading`, etc.) must detect the `±9.9E+37` sentinel and raise a typed
   `Agilent34411AOverloadError` (a new leaf under `Agilent34411ADeviceError`) rather
   than handing the caller a number that looks plausible but is a documented "out of
   range" marker — the same "fail clearly instead of silently returning a
   misleading value" standard already applied to `rf_agilent33220a`'s empty-slot
   memory recall and `rf_tbs1000c`'s waveform-block length handling.
4. **`CALCulate:FUNCtion NULL` must never be sent.** The manual explicitly documents
   this value as deprecated 34401A-compatibility-only; the driver's per-function null
   keywords must always use `[SENSe:]<function>:NULL[:STATe]`/`:NULL[:VALue]`, never
   the `CALCulate` path, so a maintainer copying a pattern from
   `rf_agilent33220a`/`rf_hp34401a` doesn't accidentally wire the wrong subsystem.
5. **Math functions are mutually exclusive.** Only one of dB/dBm/statistics/limit-test
   can be active at a time (`CALCulate:FUNCtion` is a single selector, not a bitmask);
   the driver must not offer a combined "enable dB and limits simultaneously" keyword,
   since the instrument itself has no such mode.
6. **NPLC/aperture range differs from the 34410A.** Because this driver targets the
   34411A specifically, its validation of `Set Integration Time NPLC`/`Set Integration
   Time Aperture` must accept the 34411A's wider ranges (NPLC down to 0.001; aperture
   down to 20 µs) — a value that's valid on this instrument must not be rejected by
   client-side validation copied uncritically from a 34410A-oriented implementation.
7. **`SYSTem:LANguage` is never written, and a non-native value is a connect-time
   error.** `Check Communication` (and, by extension, `Connect`) shall query
   `SYSTem:LANguage?` and raise a typed `Agilent34411AConfigurationError` if it does
   not read back `"34411A"` — a unit left in 34401A/34410A emulation mode would
   silently break most of this driver's command surface (task §2), and that failure
   mode must surface immediately at connect time, not as a confusing downstream SCPI
   error on the first real measurement command.

## 7. Required connection keywords (RFDS-002 canonical, primary API)

Identical set and semantics to `rf_agilent33220a`/`rf_tbs1000c` (task §7 in both):
`Connect(resource=None, alias="default", timeout_s=None, **options)` (VISA resource
string, or `resource=None` + `options[simulated]=True` for the bundled simulator) →
RFDS-002 §12.1 connection-state dictionary; `Disconnect(alias=None)` (idempotent);
`Is Connected(alias=None)` → bool, never raises for a missing session;
`Get Connection State(alias=None, refresh=False)`; `Check Communication(alias=None)`
(issues `*IDN?`); `Get Identity(alias=None, refresh=True)`; `Switch Multimeter`/
`Get Active Multimeter`/`List Multimeter Connections` for multi-alias sessions
(recommended, matching every other multi-instrument package in this repository).

## 8. Measurement configuration keywords

One keyword group per measurement function, all delegating to the `[SENSe:]<function>`
subsystem (task §2):

- **Function selection:** `Set Function`/`Get Function` (`FUNCtion "<name>"`).
- **DC voltage / DC current:** `Set Integration Time NPLC`, `Set Integration Time
  Aperture`, `Set Range`, `Set Auto Range`, `Set Input Impedance Auto` (DCV only,
  100 mV/1 V/10 V ranges), `Set Auto Zero`, `Set Null`, `Get Null Value` — each scoped
  per-function via a `function` parameter rather than one keyword per function ×
  parameter, to avoid an unmanageable keyword count (this repository's convention,
  matching how `rf_agilent33220a` scoped its modulation keywords by an explicit
  parameter rather than one keyword per modulation type where the underlying command
  shape is identical).
- **AC voltage / AC current:** `Set AC Filter Bandwidth`, `Set Range`, `Set Auto
  Range`, `Set Null`.
- **2-wire / 4-wire resistance:** `Set Integration Time NPLC/Aperture`, `Set Range`,
  `Set Auto Range`, `Set Offset Compensation`, `Set Auto Zero` (2-wire only — 4-wire is
  always auto-zero-on per the manual, and the driver must reject an explicit
  `Set Auto Zero` call for 4-wire with a typed validation error rather than silently
  accepting and ignoring it), `Set Null`.
- **Frequency / Period:** `Set Gate Time` (aperture, in seconds), `Set Range`
  (acts on the ac input voltage level), `Set Auto Range`, `Set AC Filter Bandwidth`,
  `Set Null`.
- **Capacitance:** `Set Range`, `Set Auto Range`, `Set Null` (no integration-time
  keyword — not applicable per §2).
- **Temperature:** `Set Temperature Probe Type` (RTD/thermistor + sub-type),
  `Set Temperature Units`, `Set Offset Compensation` (RTD only), `Set Auto Zero`
  (2-wire only, same 4-wire-always-on rule as resistance), `Set Integration Time
  NPLC/Aperture`, `Set Null`.
- **Continuity / Diode:** no configuration keywords (fixed ranges per §2); only
  `Set Function` + a measurement keyword apply.
- **Readback:** `Get Measurement Settings` → a dataclass snapshot appropriate to the
  currently selected function (mirrors `rf_agilent33220a`'s `Get Output Settings`).
- **Taking a reading:** `Get Immediate Measurement` (`READ?`, blocking, immediate
  trigger), `Get Reading` (`FETCh?`, retrieves a reading already triggered), each
  detecting and raising on the `±9.9E+37` overload sentinel per task §6 item 3.

## 9. Math, triggering, and sampling keywords

- **Math (`CALCulate:` subsystem, task §2 and §6 item 4/5):** `Enable dB Measurement`/
  `Disable Math`, `Set dB Reference`, `Enable dBm Measurement`, `Set dBm Reference
  Resistance` (validated against the documented discrete resistance list —
  50/75/93/.../8000 Ω — client-side, before any device write), `Enable Statistics`,
  `Get Statistics` (returns average/min/max/stddev/peak-to-peak/count as one
  dataclass), `Clear Statistics`, `Enable Limit Test`, `Set Limits` (low, high;
  validated `low < high` client-side before any device write), `Get Limits`,
  `Disable Math`.
- **Trigger:** `Set Trigger Source` (`IMMediate`/`EXTernal`/`BUS`/`INTernal` — the
  driver must raise a typed validation error if `INTernal` is requested on a
  non-34411A/L4411A-eligible function, since this instrument's manual restricts
  internal/level triggering to ac/dc voltage, ac/dc current, and 2-/4-wire resistance
  only), `Set Trigger Level`, `Set Trigger Slope`, `Set Trigger Delay`,
  `Set Trigger Delay Auto`, `Get Trigger Settings`.
- **Sampling:** `Set Trigger Count` (`TRIGger:COUNt`, the outer trigger-event count —
  distinct from sample count per task §2), `Set Sample Count`, `Set Sample Source`
  (`AUTO`/`TIMer`), `Set Sample Timer Interval` (only meaningful when sample source is
  `TIMer`), `Set Pre-Trigger Sample Count` (must validate
  `pretrigger_count < sample_count` client-side, matching the manual's own
  constraint, before any device write), `Trigger Now` (bare `INITiate`, only
  meaningful when trigger source is `BUS`, same "requires BUS source" guard pattern
  already implemented in `rf_agilent33220a.driver.Agilent33220A.trigger_now`).

## 10. Reading memory and data logging keywords

Confirmed in full against the Command Quick Reference (task §2) — no open questions
remain for this section.

- **Volatile reading memory:** `Get Latest Reading` (`FETCh?`), `Get Most Recent
  Reading` (`DATA:LAST?`), `Get Reading Count` (`DATA:POINts?`),
  `Drain Readings` (`DATA:REMove? <count>` — explicit "drain" name because this call
  *removes* what it reads, FIFO order, matching the same "erasing read must not be a
  surprise" naming rule already applied to `Drain Non-Volatile Readings` below).
- **Non-volatile memory / remote-driven data logging:** `Copy Readings To
  Non-Volatile Memory` (`DATA:COPY NVMEM, RDG_STORE` — the confirmed remote mechanism
  for persisting a batch of triggered readings; a Robot suite configures
  `Set Sample Count`, triggers via `Trigger Now`/an external trigger/immediate
  triggering, then calls this keyword to persist the batch), `Get Non-Volatile Reading
  Count` (`DATA:POINts? NVMEM`), `Get Non-Volatile Readings` (`DATA:DATA? NVMEM`),
  `Clear Non-Volatile Readings` (`DATA:DELete NVMEM`), `Drain Non-Volatile Readings`
  (`R? [<max_count>]`).
- The front-panel Data Logger *wizard* (start delay/interval/count-or-duration,
  pre-triggering) has no remote-interface equivalent in either source consulted —
  `DATA:COPY NVMEM, RDG_STORE` is confirmed as the actual, complete remote-driven data
  logging mechanism, so no keyword is deferred here; this section's scope is final.

## 11. Instrument state storage keywords

Confirmed in full against the Command Quick Reference (task §2) — no open questions
remain for this section; the originally-guessed `*SAV`/`*RCL`-with-slot-number shape
was correct.

- `Save Setup To Instrument Memory(slot)` (`*SAV {0|1|2|3|4}`) / `Restore Setup From
  Instrument Memory(slot)` (`*RCL {0|1|2|3|4}`, guarded by `MEMory:STATe:VALid?`
  first — reject an unsaved slot client-side with a typed error rather than sending
  `*RCL` and letting the instrument decide, per task §2) for the 5 non-volatile states
  (0–4, where 0 is the power-down-recall state).
- `Get Instrument Memory Catalog` (`MEMory:STATe:CATalog?`), `Rename Instrument
  Memory Slot(slot, name)` (`MEMory:STATe:NAME`), `Get Instrument Memory Slot Name`
  (`MEMory:STATe:NAME?`), `Delete Instrument Memory Slot(slot)`
  (`MEMory:STATe:DELete`), `Delete All Instrument Memory Slots`
  (`MEMory:STATe:DELete:ALL`), `Is Instrument Memory Slot Valid(slot)`
  (`MEMory:STATe:VALid?`), `Get Instrument Memory Slot Count` (`MEMory:NSTates?`).
- `Set Power-On State Recall(enabled)` (`MEMory:STATe:RECall:AUTO`) and
  `Set Power-On State(slot)` (`MEMory:STATe:RECall:SELect`) select whether, and which,
  stored state is recalled at power-on instead of factory defaults.
- No `*LRN?`-equivalent host-file save/restore command exists for this instrument
  (confirmed absent from both sources) — state persistence here is entirely
  instrument-resident. A host-file `Save Setup`/`Restore Setup` pair (as implemented
  for `rf_agilent33220a`/`rf_tbs1000c`) is **out of scope** for this driver, not merely
  deferred.

## 12. Raw SCPI escape hatch

- `Enable Raw SCPI` requires the exact confirmation string `"ENABLE RAW SCPI"`
  (matching `rf_ngi_n83624`/`rf_eresistor`/`rf_tbs1000c`/`rf_agilent33220a`).
- `Raw SCPI Query`/`Raw SCPI Write` document that they bypass typed validation — this
  is also the sanctioned path to calibration commands (§6 item 2), which are
  deliberately not wrapped as typed keywords.

## 13. Simulator requirements

The bundled simulator shall support, deterministically and without hardware:

- `*IDN?`, `*CLS`, `*RST`, `*TST?`, `SYSTem:ERRor?`, `SYSTem:PRESet`.
- Function selection and per-function configuration state (NPLC/aperture, range/
  autorange, auto-zero, offset compensation, AC filter bandwidth, null) — read back
  what was set, same as `rf_agilent33220a`'s simulator pattern.
- A deterministic, configurable measurement value per function so
  `Get Immediate Measurement`/`Get Reading` are genuinely testable (e.g. a settable
  "next reading" value per function, defaulting to a fixed in-range value), plus a
  test hook to force the `±9.9E+37` overload sentinel so task §6 item 3's typed-error
  behavior can be exercised offline.
- Math subsystem state (`CALCulate:FUNCtion`, dB/dBm reference, statistics
  accumulation across simulated readings, limit values) sufficient to exercise every
  math keyword in §9.
- Trigger/sample subsystem state (source, level, slope, delay, sample count,
  pre-trigger count) — read back what was set; `INTernal` source must be rejected by
  the simulator too when the active function doesn't support it, so the client-side
  validation in task §6 item — matching driver behavior — is exercised against a
  simulator that actually enforces the same rule, not one that silently accepts
  anything.
- Volatile reading memory (`FETCh?`, `DATA:LAST?`, `DATA:POINts?`, `DATA:REMove?`) and
  non-volatile reading memory (`DATA:COPY NVMEM, RDG_STORE`, `DATA:DATA? NVMEM`,
  `DATA:DELete NVMEM`, `DATA:POINts? NVMEM`, `R?`) each as an in-memory list, with
  deterministic seeded content for tests.
- Instrument memory states 0–4 as an in-memory dict keyed by slot, backing `*SAV`/
  `*RCL` and the full `MEMory:STATe:*` family (§11) — including `MEMory:STATe:VALid?`
  correctly reporting `False` for a never-saved slot, so the client-side
  reject-unsaved-slot behavior (§11) is exercised against a simulator that enforces
  the same rule the real instrument does.
- `ROUTe:TERMinals?` returning a fixed simulated value (`"FRON"`); no write path, same
  as the real instrument.

## 14. Tests

### 14.1 Python unit tests

Cover at minimum:

1. Simulator connect and identity.
2. Per-function configuration round-trips (NPLC/aperture, range/autorange, auto-zero,
   offset compensation, AC filter bandwidth) for at least DC voltage, AC voltage,
   4-wire resistance, and frequency.
3. `Get Immediate Measurement`/`Get Reading` raise `Agilent34411AOverloadError`
   specifically (not a generic device error) when the simulator is forced into the
   `±9.9E+37` overload state.
4. 4-wire resistance/temperature reject an explicit `Set Auto Zero` call with a typed
   validation error (task §8, always-on-for-4-wire rule).
5. Math functions are mutually exclusive — enabling one deselects any previously active
   one, matching the instrument's single-selector `CALCulate:FUNCtion` semantics.
6. `Set dBm Reference Resistance` rejects a value outside the documented discrete list
   before any device write.
7. `Set Limits` rejects `low >= high` before any device write.
8. Trigger source `INTernal` is rejected (typed validation error) when set against a
   function the manual excludes (e.g. capacitance, frequency/period, temperature).
9. `Set Pre-Trigger Sample Count` rejects a pre-trigger count ≥ sample count before any
   device write.
10. Raw SCPI guard (rejects without exact confirmation text).
11. Robot data-conversion helpers (dataclass/enum → dict/scalar) — reuse
    `rf_agilent33220a`'s test shape.
12. Multi-alias session handling.
13. Non-volatile reading memory round-trip: trigger/seed readings, `Copy Readings To
    Non-Volatile Memory`, then `Get Non-Volatile Reading Count`/`Get Non-Volatile
    Readings`/`Clear Non-Volatile Readings` reflect it correctly.
14. Instrument memory save/restore round-trip (§11): save to a slot, mutate
    configuration, restore, confirm it comes back; restoring a never-saved slot raises
    a typed error instead of sending `*RCL` and letting the instrument decide.

### 14.2 Robot acceptance tests

Must run offline against the simulator and cover: identity, connect/disconnect
lifecycle (including the RFDS-002 generic keywords), DC and AC voltage measurement
configuration and an immediate measurement, 4-wire resistance with offset compensation,
at least one math function (statistics), a trigger-source/sample-count round trip, and
a non-volatile-memory read/clear round trip.

### 14.3 Hardware tests (RFDS-019 conformance)

Create a marked hardware test plan; do not run automatically in CI. Include, against a
real 34411A unit:

- identity and firmware capture over all three interfaces (GPIB, USB, LAN) at least
  once each, to confirm the single-VISA-backend design (§5) genuinely works across all
  of them, matching the equivalent test already planned for `rf_agilent33220a`;
- cross-check a DC voltage and a 4-wire resistance reading against an independent
  reference standard or calibrator;
- confirm the `±9.9E+37` overload sentinel against a real out-of-range input on a
  manually-selected fixed range;
- confirm `MEMory:`/`*SAV`/`*RCL` state save/restore and `DATA:COPY NVMEM, RDG_STORE`
  non-volatile-memory readback against real firmware;
- confirm internal (level) triggering and pre-triggering behavior on real hardware,
  since neither can be meaningfully validated by a simulator beyond state-tracking;
- confirm `SYSTem:LANguage?` reads back `"34411A"` on a factory-default unit, and that
  the connect-time check (§6 item 7) correctly rejects a unit deliberately switched to
  `34401A`/`34410A` emulation mode.

## 15. Documentation and examples

- `README.md` following the `rf_agilent33220a`/`rf_tbs1000c` house style: title +
  version + Gate status, install (with `[visa,visa-py]` extras), a runnable Robot
  Framework quick-start example against the simulator, a full keyword list grouped by
  section, and a safety-relevant-behaviors section (overload handling, front/rear
  switch read-only, calibration out of scope).
- `examples/`: at minimum an identify suite, a DC/AC measurement configuration suite,
  a math-and-statistics suite, and a non-volatile-memory suite (matching the four
  examples already delivered for `rf_agilent33220a`).
- `ai/ai_contract.yaml`/`ai/agilent34411a_ai_contract.yaml`-equivalent (RFDS-017) is
  Gate 4 work, not Gate 2 — do not create it yet (matches the explicit Gate status
  already recorded for `rf_agilent33220a`/`rf_tbs1000c` in their own READMEs). Note for
  whoever reaches Gate 4: this repository renames the per-driver contract file to
  `<library>_ai_contract.{yaml,lock}` (a repository-specific deviation from RFDS-017's
  literal fixed-name convention, applied across the other seven driver packages) — this
  driver's contract should be named `agilent34411a_ai_contract.yaml`/`.lock` for
  consistency when that work starts.

## 16. Scripts

None required for Gate 1/Gate 2. If an AI-contract generator script becomes necessary
at Gate 4, follow the `rf_agilent33220a`-adjacent precedent of a hand-maintained
contract with a `pytest`-based conformance check, rather than introducing a new
generator pattern, unless the driver's keyword surface is large enough to warrant one
(this repository has both patterns in use across its packages; pick whichever the
actual keyword count at Gate 4 time makes more maintainable).

## 17. CI and release checks

Deferred to Gate 4/5 per RFDS-020 — not in scope for this task document.

## 18. Acceptance criteria

Gate 2 (Core Implementation) is complete when:

- [ ] Core driver (`agilent34411a`) implements connection lifecycle, all measurement
  functions in §8, math in §9, trigger/sample in §9, reading memory/data logging in
  §10, instrument memory state storage in §11, and the raw SCPI escape hatch in §12,
  each backed by the bundled simulator.
- [ ] Robot Framework adapter (`rf_agilent34411a`) wraps every implemented core method
  as a keyword, with RFDS-002 canonical connection keywords as the primary API.
- [ ] Unit tests (§14.1) and Robot acceptance tests (§14.2) pass; `ruff`/`mypy`/`build`
  are clean.
- [ ] README and examples (§15) are complete for everything actually implemented.
- [ ] The two remaining open questions in §19 (AC/frequency range numbers,
  `CONFigure`/`MEASure?` parameterized syntax) are either resolved or the
  corresponding client-side validation is simply omitted rather than guessed — neither
  blocks Gate 2 as scoped, since §8 routes all configuration through `[SENSe:]` and
  range validation is optional, not required, for those two functions.

## 19. Open questions for Gate 1

This task document was grounded in two sources read directly during Gate 1 research:
the Agilent 34410A/11A/L4411A *User's Guide* (34410-90001, 4th ed., Feb 2007), and the
*Agilent 34410A/11A Command Quick Reference* (Agilent Technologies, Jan 2006) — a
complete SCPI syntax listing that resolved every command-mnemonic question the first
research pass left open (temperature units, the `MEMory:` state-storage subsystem, and
the actual remote-driven data-logging mechanism). Four of the original six open
questions are resolved as a result and have been folded into §2/§9/§10/§11 directly,
with a note at each resolution point. The two genuinely remaining open items, both
low-priority and non-blocking for Gate 2 as scoped:

1. **AC voltage/current and frequency/period range values and accuracy.** DC voltage,
   resistance, DC current, capacitance, continuity, and diode ranges were transcribed
   from the "DC Characteristics" table in the User's Guide's §5 "Specifications" during
   Gate 1 research; the "AC Characteristics" and "Frequency and Period Characteristics"
   tables in the same chapter were not read, and the Command Quick Reference lists
   command syntax only, not numeric range/accuracy values. This driver does not
   require these numbers for Gate 2 — §8's AC voltage/current and frequency/period
   keywords pass range values straight through to `[SENSe:]<function>:RANGe[:UPPER]`
   without client-side bounds-checking (the instrument itself rejects an out-of-range
   value with a normal SCPI error), so no keyword is blocked. Pull these numbers only
   if a future revision adds client-side range validation for these functions.
2. **`CONFigure`/`MEASure?` full parameterized syntax beyond what the Command Quick
   Reference already confirmed.** The Command Quick Reference confirms the outer shape
   for every function (e.g. `CONFigure[:VOLTage][:DC] [{<range>|AUTO|MIN|MAX|DEF}
   [,{<resolution>|MIN|MAX|DEF}]]`, `MEASure[:VOLTage][:DC]? [...]` with the same
   parameter shape) — this is no longer meaningfully open for the commands this task
   actually uses. It remains listed only because this driver deliberately routes all
   configuration through the `[SENSe:]` subsystem instead of `CONFigure`/`MEASure?`
   (§2), so a future revision adding a `Configure Measurement` convenience keyword
   analogous to `rf_agilent33220a`'s `Configure Output` should re-verify the exact
   resolution-parameter semantics for the specific function it targets before shipping.
