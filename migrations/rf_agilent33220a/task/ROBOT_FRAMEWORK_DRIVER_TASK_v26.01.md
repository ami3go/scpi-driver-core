# Task: Robot Framework Driver for Agilent 33220A

**Task revision:** 26.01-draft
**Date:** 2026-08-01
**Target package:** `rf_agilent33220a_v26.01.zip`
**Required internal repository root:** `rf_agilent33220a/`

## 1. Objective

Create a Robot Framework library for the Agilent (now Keysight) 33220A 20 MHz function/
arbitrary waveform generator, built on a new typed Python core driver (`agilent33220a`)
that owns SCPI command construction and response parsing. This instrument sources a
signal, not power — its output is impedance-limited (fixed 50 Ω series output, ±10 Vdc max
into an open circuit) — so the physical risk is much lower than the power supplies and
loads already in this repository, but it is not a pure measurement instrument either:
enabling its output injects a real signal into whatever is connected. The primary
engineering risk here is **an unintended signal appearing at the output**, not electrical
hazard to a person.

This package shall build the RFDS-002 canonical connection lifecycle
(`Connect` / `Disconnect` / `Is Connected` / `Get Connection State` / `Check Communication` /
`Get Identity`) as the **primary, documented API** from the outset, matching
`rf_hp34401a`, `rf_votsch_climate_chamber`, and `rf_tbs1000c` — not retrofitted later.

The package must support offline verification without hardware and define a separate,
explicit qualification process for the exact 33220A unit, firmware, and DUT wiring.

## 2. Instrument facts (source: Agilent 33220A User's Guide, part number 9018-04437,
FrameMaker-produced PDF dated 2007/rev. 2012 — verify against the exact unit's firmware
before Gate 2)

- **Transport:** GPIB (IEEE-488), USB, and LAN (LXI Class C) are **all standard** — unlike
  `rf_tbs1000c`, there is no optional-adapter ambiguity here. All three are reachable
  through a single VISA resource string (`pyvisa`), so this driver needs only **one**
  transport backend plus the simulator — no per-interface backend code, matching the
  pattern already used by `rf_bk8500b`/`rf_keysight_n6700`.
- **Command grammar:** standard SCPI (`[]` optional, `{}` parameter choices, `<>`
  substitution, `|` alternatives), fully SCPI-1999-compliant per the manual's own claim.
- **Single output, no channel concept.** Unlike the oscilloscopes/loads/power supplies in
  this repository, the 33220A has exactly one output connector — driver keywords take no
  `channel` argument.
- **Command groups relevant to this driver** (see the manual for full argument grammar):
  - `*IDN?`, `*CLS`, `*RST`, `*TST?`, `SYSTem:VERSion?`, `SYSTem:ERRor?` — standard/common
    and error-queue commands.
  - `SYSTem:KLOCk[:STATe] {OFF|ON}`, `SYSTem:KLOCk:EXCLude {NONE|LOCal}` — front-panel
    lockout. Genuinely useful for an automated run: prevents an operator from changing
    settings by touching the instrument mid-test. `DISPlay {OFF|ON}`, `DISPlay:TEXT <quoted
    string>` / `:CLEar`, `SYSTem:BEEPer[:STATe]` — cosmetic front-panel commands, lower
    priority but cheap to wrap.
  - `APPLy:{SINusoid|SQUare|RAMP|PULSe|NOISe|DC|USER} [<freq>[,<ampl>[,<offset>]]]`,
    `APPLy?` — the simplified one-shot configuration command. **Silently turns the output
    ON as a side effect** (see §6).
  - `FUNCtion {SINusoid|SQUare|RAMP|PULSe|NOISe|DC|USER}`, `FREQuency`, `VOLTage`,
    `VOLTage:OFFSet`, `VOLTage:HIGH`/`:LOW`, `VOLTage:RANGe:AUTO`, `VOLTage:UNIT
    {VPP|VRMS|DBM}`, `FUNCtion:SQUare:DCYCle`, `FUNCtion:RAMP:SYMMetry` — low-level output
    configuration (the non-side-effecting alternative to `APPLy`).
  - `OUTPut {OFF|ON}`, `OUTPut:LOAD {<ohms>|INFinity|...}`, `OUTPut:POLarity
    {NORMal|INVerted}`, `OUTPut:SYNC {OFF|ON}` — output enable/impedance/polarity.
    **`OUTPut` itself defaults to OFF after `*RST`** (confirmed in the manual's detailed
    command entry, not just the summary table).
  - `PULSe:PERiod`, `FUNCtion:PULSe:HOLD/:WIDTh/:DCYCle/:TRANsition` — pulse shape.
  - `AM:*`, `FM:*`, `PM:*`, `FSKey:*`, `PWM:*` — amplitude/frequency/phase modulation,
    frequency-shift keying, pulse-width modulation. Each has its own `:STATe {OFF|ON}`.
  - `FREQuency:STARt/:STOP/:CENTer/:SPAN`, `SWEep:SPACing/:TIME/:STATe`,
    `MARKer:FREQuency`, `MARKer {OFF|ON}` — frequency sweep.
  - `BURSt:MODE {TRIGgered|GATed}`, `BURSt:NCYCles`, `BURSt:INTernal:PERiod`,
    `BURSt:PHASe`, `BURSt:STATe`, `BURSt:GATE:POLarity` — burst mode.
  - `TRIGger:SOURce {IMMediate|EXTernal|BUS}`, `TRIGger:SLOPe`, `TRIGger` (bare, executes an
    immediate trigger), `*TRG`, `OUTPut:TRIGger {OFF|ON}`, `OUTPut:TRIGger:SLOPe` — trigger
    configuration for sweep/burst.
  - `DATA VOLATILE, <value>, <value>, ...`, `DATA:DAC VOLATILE, {<binary
    block>|<value>,...}`, `DATA:COPY`, `DATA:CATalog?`, `DATA:DELete`, `DATA:DELete:ALL`,
    `DATA:ATTRibute:AVERage?/:CFACtor?/:POINts?/:PTPeak?`, `FUNCtion:USER {<arb
    name>|VOLATILE}`, `FORMat:BORDer {NORMal|SWAPped}` — arbitrary waveform definition and
    selection. Five built-in arbitrary waveforms exist: `EXP_RISE`, `EXP_FALL`, `NEG_RAMP`,
    `SINC`, `CARDIAC`.
  - `*SAV {0|1|2|3|4}`, `*RCL {0|1|2|3|4}`, `MEMory:STATe:NAME/:DELete/:RECall:AUTO/
    :VALid?/:CATalog?`, `MEMory:NSTates?` — numbered instrument-state storage. State 0 is
    the power-down state; states 1-4 are user-defined. No instrument filesystem is involved
    (unlike `rf_tbs1000c`) — this is pure internal memory.
  - `*LRN?` — **fully documented here, unlike the TBS1000C case**: "Query the function
    generator and return a string of SCPI commands containing the current settings (learn
    string). You can then send the string back to the instrument to restore this state at
    a later time." This can be the primary `Save Setup`/`Restore Setup` mechanism with high
    confidence, no fallback-design-uncertainty needed.
  - `SYSTem:COMMunicate:GPIB:ADDRess`, `SYSTem:COMMunicate:LAN:*` (IP address, AutoIP, MAC,
    mDNS/NETBios, Telnet prompt/welcome message) — interface configuration; out of scope
    for v26.01 keywords (configuring the network identity of the instrument itself is a
    bench-setup concern, not a per-test keyword).
  - `*STB?`, `*SRE`, `*ESR?`, `*ESE`, `*CLS`, `STATus:QUEStionable:CONDition?/[:EVENt]?/
    :ENABle`, `STATus:PRESet`, `*PSC` — status/event system, used for `Check Communication`
    and post-write error verification.
  - `CAL?`, `CAL:SECure:STATe/:CODE`, `CAL:SETup`, `CAL:VALue`, `CAL:COUNt?`, `CAL:STRing` —
    calibration. Out of scope for v26.01 keywords: this is a metrology procedure requiring
    the instrument's calibration security code, not a routine test-suite operation. A guarded
    raw-SCPI escape hatch covers it if a bench genuinely needs it.

## 3. Mandatory package structure

```text
rf_agilent33220a/
├── rf_agilent33220a/        Robot Framework Python library (adapter)
├── agilent33220a/           new typed core driver: transport, SCPI, arb waveform helpers
├── examples/                at least 10 Robot suites
├── scripts/                 Windows and Linux setup/test/example/build scripts
├── tests/                   Python unit tests, Robot acceptance tests, RFDS-019 conformance
├── task/                    this file, plus the task readiness review
├── history/                 change history for every release
├── review/                  implementation review and fix records
├── guide/                   PyCharm, Robot Framework, and hardware setup guides
├── docs/                    GitHub Pages/MkDocs content
├── ai/                      RFDS-017 AI driver contract and lock
├── config/                  RFDS-014 schema.json / schema.lock / default.json / example.json
├── .github/workflows/       CI and Pages workflows
├── README.md
├── CHANGELOG.md
├── AGENTS.md
├── pyproject.toml
├── mkdocs.yml
└── LICENSE
```

No `src/` directory is permitted (RFDS-005 §6.1).

## 4. Versioning and packaging

1. ZIP filename shall be `rf_agilent33220a_v26.01.zip`.
2. ZIP shall contain exactly one top-level folder named `rf_agilent33220a`.
3. Human-facing release label shall be `v26.01`.
4. Python distribution version shall be PEP 440-compatible `26.1`.
5. Distribution name: `robotframework-agilent33220a`.
6. The Python import shall be `rf_agilent33220a`.
7. The primary Robot import shall be:

```robot
Library    rf_agilent33220a.Agilent33220ALibrary
```

## 5. Architecture

### 5.1 Layers

1. **Robot Framework layer** — keyword names, Robot-friendly argument conversion,
   assertions, RFDS-002 connection-state dictionary, cleanup.
2. **Typed Python driver layer** (`agilent33220a`) — SCPI formatting/parsing, output/
   modulation/sweep/burst/arb-waveform models, enums, validation.
3. **Transport layer** — VISA via `pyvisa`, accepting any resource string the instrument
   supports (GPIB, USB, or LAN/LXI — one backend, not three), plus a deterministic
   in-process simulator.
4. **Instrument layer** — the physical 33220A and whatever DUT is connected to its output.

### 5.2 Design constraints

- Robot keywords shall not duplicate SCPI formatting logic; that belongs in
  `agilent33220a`.
- Raw SCPI shall be an explicitly guarded escape hatch, consistent with every other driver
  in this repository (RFDS-006 §19 prohibits silent duplicate protocol construction). This
  is also where calibration (`CAL:*`) lives for v26.01 (§2).
- Exceptions shall follow RFDS-007: an `Agilent33220AError`-rooted hierarchy
  (`Agilent33220AConnectionError`, `Agilent33220ATimeoutError`, `Agilent33220AProtocolError`,
  `Agilent33220AValidationError`, `Agilent33220ADeviceError`, `Agilent33220ASafetyError`),
  not bare built-ins raised at the keyword boundary.
- **Every keyword that configures the output via the high-level path must not leave the
  output silently enabled as a side effect of that configuration** (see §6 item 1) — the
  driver's own default behavior must not inherit `APPLy`'s surprise.

### 5.3 Host-side configuration profile (RFDS-014, `config/`)

Mirrors `rf_tbs1000c`'s minimal, honestly-scoped approach — no device safety envelope to
persist for this instrument, just host-side connection/behavior defaults:

```json
{
  "resource": "USB0::0x0957::0x0407::<serial>::INSTR",
  "timeout_s": 5.0,
  "confirm_output_enable": true
}
```

- `resource` — optional default for `Connect`, matching `rf_tbs1000c`'s pattern.
- `timeout_s` — optional default connection timeout.
- `confirm_output_enable` — if true (default), `Enable Output` logs at `INFO` with the
  current function/frequency/amplitude/offset before enabling, so a Robot log always shows
  what was about to be injected into the DUT and when — this is the AWG's equivalent of the
  scope's `AUTOSet` logging requirement (task §6 item 1).

## 6. Signal-integrity and safety requirements

This instrument sources a real signal, but at low, impedance-limited levels (±10 Vdc max
into an open circuit, fixed 50 Ω series output) — "safety" here is mostly about not
surprising a connected DUT with an unexpected signal, plus the one real electrical
consideration (external overvoltage handling).

1. **`APPLy` silently enables the output** — confirmed in the manual: "The APPLy command
   overrides the current OUTP command setting and automatically enables the Output
   connector." Any driver keyword built on `APPLy` shall document this explicitly and, by
   default, restore the output to its pre-call state afterward unless the caller explicitly
   asked for the output to end up enabled — the driver's own defaults must not silently
   energize the output just because the underlying vendor command does. `OUTPut` itself
   correctly defaults to OFF after `*RST`; the driver should not undermine that default
   through its higher-level keywords.
2. **`Enable Output` is a distinct, explicit keyword**, never a side effect of configuring
   frequency/amplitude/function/modulation/sweep/burst. Logged at `INFO` with the current
   configuration (§5.3) so a Robot log always shows what was live and when.
3. **External overvoltage on the output connector auto-disables the output and posts an
   error** (documented instrument behavior). `Check Communication`/error-queue reads after
   any output-affecting write shall surface this as a typed `Agilent33220ADeviceError`
   rather than a generic transport failure, so a caller can distinguish "the instrument
   protected itself from an overvoltage" from "the write failed."
4. **Amplitude/offset relationship must be validated before sending**, matching the
   manual's own documented constraint: `Vpp < 2 × (Vmax − |Voffset|)`. Reject client-side
   with a clear message rather than let the instrument silently clamp or generate a
   "Settings conflict" error the caller has to go decode. This is a real signal-integrity
   limit, not an arbitrary argument-shape check, so it raises `Agilent33220ASafetyError`
   (RFDS-007 `DriverSafetyError` → `LimitViolation` family), not the generic
   `Agilent33220AValidationError`.
5. **Function changes can silently reduce frequency/amplitude** (documented: switching to a
   function with a lower max frequency/amplitude auto-adjusts the current setting and
   raises a "Settings conflict" instrument error). `Set Function` shall check the error
   queue immediately after and raise a typed error naming the actual adjusted value, rather
   than leaving the caller to discover it was silently changed on a later read.
6. **Arbitrary waveform upload (`DATA`/`DATA:DAC`) writes to volatile memory only** unless
   explicitly copied with `DATA:COPY ... , VOLATILE` — the task doc's arb-waveform keywords
   shall make this volatility explicit in their documentation, mirroring the scope driver's
   "a screen capture reflects whatever is currently displayed" honesty about what a keyword
   actually guarantees.

## 7. Required connection keywords (RFDS-002 canonical, primary API)

- `Connect(resource=None, alias="default", timeout_s=None, **options)` → RFDS-002 §12.1
  connection-state dictionary. `resource` is any VISA resource string (GPIB/USB/LAN); omit
  for the bundled simulator (`resource=None` + `options[simulated]=True`).
- `Disconnect(alias=None)` — idempotent.
- `Is Connected(alias=None)` → bool, never raises for a missing session.
- `Get Connection State(alias=None, refresh=False)` → RFDS-002 §12.1 dictionary.
- `Check Communication(alias=None)` → bool, raises on failure (issues `*IDN?`).
- `Get Identity(alias=None, refresh=True)` → stable identity string from `*IDN?`.
- `Switch Generator` / `Get Active Generator` / `List Generator Connections` — only if
  multi-alias sessions are implemented (recommended, matching every other multi-instrument
  package in this repository — useful for a bench with more than one 33220A).

No instrument-specific `Connect To ...` keyword is required; if one is added for
readability, it shall be a documented alias that calls `Connect` internally.

## 8. Output configuration keywords

- `Set Function {SINusoid|SQUare|RAMP|PULSe|NOISe|DC|USER}` / `Get Function` — guarded per
  §6 item 5.
- `Set Frequency`, `Get Frequency` (Hz; `MINimum`/`MAXimum` accepted as documented sentinels)
- `Set Amplitude`, `Get Amplitude` — validated per §6 item 4.
- `Set Amplitude Unit {VPP|VRMS|DBM}` / `Get Amplitude Unit`
- `Set Offset`, `Get Offset` — validated per §6 item 4.
- `Set Output Load {<ohms>|INFinity}` / `Get Output Load`
- `Set Output Polarity {NORMal|INVerted}` / `Get Output Polarity`
- `Set Square Duty Cycle`, `Get Square Duty Cycle` (`FUNCtion:SQUare:DCYCle`)
- `Set Ramp Symmetry`, `Get Ramp Symmetry` (`FUNCtion:RAMP:SYMMetry`)
- `Configure Output` — the guarded, `APPLy`-backed convenience keyword. Sets function,
  frequency, amplitude, and offset in one call; restores prior output-enabled state per §6
  item 1 unless `enable_output=True` is explicitly passed.
- `Enable Output` / `Disable Output` / `Is Output Enabled` — explicit, per §6 item 2.
- `Lock Front Panel` / `Unlock Front Panel` / `Is Front Panel Locked` — `SYSTem:KLOCk`.
  Recommended in every suite that changes output settings, so an operator standing at the
  bench can't hand-edit a setting mid-test.
- `Set Display Text` / `Clear Display Text` / `Enable Display` / `Disable Display` —
  cosmetic; useful for showing a human-readable test-step label on the instrument itself.

## 9. Pulse, modulation, sweep, and burst keywords

- `Configure Pulse(period, width_or_duty, transition_time)` — `PULSe:PERiod`,
  `FUNCtion:PULSe:HOLD`, `:WIDTh`/`:DCYCle`, `:TRANsition`.
- `Configure Amplitude Modulation(shape, frequency, depth_percent, source)` /
  `Enable Amplitude Modulation` / `Disable Amplitude Modulation` — `AM:*`.
- `Configure Frequency Modulation(...)` / `Enable/Disable Frequency Modulation` — `FM:*`.
- `Configure Phase Modulation(...)` / `Enable/Disable Phase Modulation` — `PM:*`.
- `Configure Frequency Shift Keying(...)` / `Enable/Disable Frequency Shift Keying` —
  `FSKey:*`.
- `Configure Pulse Width Modulation(...)` / `Enable/Disable Pulse Width Modulation` —
  `PWM:*`.
- `Configure Frequency Sweep(start, stop, spacing, time)` / `Enable Sweep` / `Disable Sweep`
  — `FREQuency:STARt/:STOP`, `SWEep:SPACing/:TIME/:STATe`.
- `Set Sweep Marker Frequency` / `Get Sweep Marker Frequency`, `Enable Sweep Marker` /
  `Disable Sweep Marker` — `MARKer:FREQuency`, `MARKer {OFF|ON}`. Drives the rear-panel
  "Sync"-adjacent marker output during a sweep; only meaningful while a sweep is active.
- `Configure Burst(mode, cycles, period, phase)` / `Enable Burst` / `Disable Burst` —
  `BURSt:*`.
- `Set Trigger Source {IMMediate|EXTernal|BUS}` / `Get Trigger Source` — shared by sweep and
  burst per the manual ("These commands are used for Sweep and Burst only").
- `Set Trigger Slope {POSitive|NEGative}` / `Get Trigger Slope`
- `Trigger Now` — bare `TRIGger`/`*TRG`, only valid when `TRIGger:SOURce BUS`.

## 10. Arbitrary waveform keywords

- `Load Arbitrary Waveform(name, values)` — `DATA VOLATILE, <value>, ...` (ASCII path) or
  `DATA:DAC VOLATILE, <binary block>` (binary path, matching `rf_tbs1000c`'s dual-encoding
  precedent for waveform data). Documents volatility explicitly per §6 item 6.
- `Copy Arbitrary Waveform To Nonvolatile(name)` — `DATA:COPY <name>` — the only way this
  driver persists an uploaded waveform past a disconnect/power cycle; explicit, never
  implicit.
- `Select Arbitrary Waveform(name)` — `FUNCtion:USER`, then `FUNCtion USER` to make it the
  active output function.
- `List Arbitrary Waveforms` — `DATA:CATalog?` / `DATA:NVOLatile:CATalog?`.
- `Delete Arbitrary Waveform(name)` / `Delete All Arbitrary Waveforms` — `DATA:DELete` /
  `DATA:DELete:ALL`.
- `Get Arbitrary Waveform Attributes(name)` — average/crest-factor/points/peak-to-peak via
  `DATA:ATTRibute:*?`.

## 11. Setup save/restore keywords

Unlike `rf_tbs1000c`, `*LRN?` is fully documented for this instrument (§2) — no
Gate-2 characterization risk carried forward here.

- `Save Setup(path, alias=None)` → `*LRN?`, written verbatim to a host file. Primary path.
- `Restore Setup(path, alias=None)` → resend the captured string; verify via
  `SYSTem:ERRor?`/the status system rather than assuming success.
- `Save Setup To Instrument Memory(slot)` / `Restore Setup From Instrument Memory(slot)` —
  `*SAV`/`*RCL {0|1|2|3|4}`. Slot 0 is the power-down state; document that saving to it is
  unusual and normally reserved for the instrument itself. `Restore Setup From Instrument
  Memory` shall check `MEMory:STATe:VALid? <slot>` first and raise a clear error for an
  empty/never-saved slot rather than calling `*RCL` on it and letting the instrument decide
  what an undefined recall means — the same "fail clearly instead of silently reconfiguring"
  standard already applied to the file-based `Restore Setup` (§14.1 item 11).
- `Restore Factory Setup(alias=None)` → `*RST`.

## 12. Raw SCPI escape hatch

- `Enable Raw SCPI` shall require an exact confirmation string
  (`"ENABLE RAW SCPI"`, matching `rf_ngi_n83624`/`rf_eresistor`/`rf_tbs1000c`).
- `Raw SCPI Query` / `Raw SCPI Write` shall document that they bypass typed validation —
  this is also the sanctioned path to calibration commands (§2), which are deliberately not
  wrapped as typed keywords in v26.01.

## 13. Simulator requirements

The bundled simulator shall support, deterministically and without hardware:

- `*IDN?`, `*CLS`, `*RST`, `*TST?`, `SYSTem:ERRor?`
- Function/frequency/amplitude/offset/output-enable state (read back what was set)
- The `APPLy` side effect on output-enable state (§6 item 1) — this is the one behavior a
  simulator absolutely must reproduce faithfully, since it's the safety-relevant surprise
  this driver is designed around.
- Front-panel lock state (`SYSTem:KLOCk`), display text/on-off state, and sweep marker
  frequency/state — read back what was set, same as every other configuration item.
- Amplitude/offset constraint checking (`Vpp < 2 × (Vmax − |Voffset|)`) sufficient to
  exercise §6 item 4's client-side validation tests
- A function-limit "Settings conflict" simulation sufficient to exercise §6 item 5
- Modulation/sweep/burst/trigger state (read back what was set; no need to simulate an
  actual analog output)
- Arbitrary waveform upload/catalog/delete against an in-memory volatile/non-volatile store
- A deterministic `*LRN?`/`*SAV`/`*RCL` implementation, consistent with `rf_tbs1000c`'s
  concatenated-command dispatch approach (`;`/`:` grammar) so `Restore Setup` genuinely
  replays state through the same command path every other keyword uses
- `MEMory:STATe:VALid?` tracking which of the five slots have actually been saved to, so
  the empty-slot-recall rejection (§11) can be tested offline

## 14. Tests

### 14.1 Python unit tests

Cover at minimum:

1. Simulator connect and identity.
2. `Configure Output` (APPLy-backed) does not leave the output enabled unless
   `enable_output=True` was passed — the core safety-behavior test for this driver.
3. `Enable Output`/`Disable Output` are the only way the output state changes as a
   side-effect-free, explicit action.
4. Amplitude/offset validation rejects `Vpp ≥ 2 × (Vmax − |Voffset|)` before any device I/O,
   raising `Agilent33220ASafetyError` specifically (not the generic validation error).
5. A simulated function-limit "Settings conflict" is surfaced as a typed error naming the
   actual adjusted value, not silently swallowed.
6. Raw SCPI guard (rejects without exact confirmation text).
7. Robot data-conversion helpers (dataclass/enum → dict/scalar).
8. Multi-alias session handling, if implemented.
9. Arbitrary waveform upload/catalog/delete round-trips against the simulator's in-memory
   store; deleting a non-existent name fails clearly.
10. `Save Setup` → `Restore Setup` round-trips against the simulator's deterministic
    `*LRN?` response (mirrors `rf_tbs1000c` test #12).
11. `Restore Setup` with corrupted/foreign file content fails clearly instead of silently
    reconfiguring the instrument (mirrors `rf_tbs1000c` test #13).
12. `Save Setup To Instrument Memory`/`Restore Setup From Instrument Memory` round-trip via
    `*SAV`/`*RCL`; recalling a slot that was never saved to raises a clear error instead of
    silently proceeding.
13. `Lock Front Panel`/`Unlock Front Panel` round-trip, and `Is Front Panel Locked` reflects
    the current state without requiring a prior explicit lock/unlock call in the same test.
14. `Set Sweep Marker Frequency`/`Enable Sweep Marker` round-trip against the simulator.

### 14.2 Robot acceptance tests

Must run offline against the simulator and cover: identity, connect/disconnect lifecycle
(including the RFDS-002 generic keywords), output configuration via both the low-level
keywords and `Configure Output`/`Enable Output`, at least one modulation mode, sweep
(including the marker keywords), burst, front-panel lock/unlock, an arbitrary waveform
upload and selection, and a setup save/restore round trip.

### 14.3 Hardware tests (RFDS-019 conformance)

Create a marked hardware test plan; do not run automatically in CI. Include, against a real
33220A unit:

- identity and firmware capture over all three interfaces (GPIB, USB, LAN) at least once
  each, to confirm the single-VISA-backend design (§5.1) genuinely works across all of them;
- confirm `APPLy`'s output-enable side effect against real firmware, and that `Configure
  Output`'s restore-prior-state behavior (§6 item 1) actually holds;
- confirm the external-overvoltage auto-disable behavior (§6 item 3) with a controlled
  overvoltage source, if the bench has one rated for this safely — otherwise document as
  UNKNOWN rather than assumed;
- amplitude/offset limit behavior at the actual boundary, cross-checked with an independent
  oscilloscope or DMM measurement;
- arbitrary waveform upload cross-checked by capturing the resulting output on a scope;
- `*LRN?`/`Save Setup`/`Restore Setup` round trip on real hardware, instrument power-cycled
  between save and restore.

## 15. Documentation and examples

Deliver, matching every other package in this repository:

- README with install, import, quick start, signal-integrity/safety notes, examples,
  test/build commands, layout, and status.
- GitHub Pages / MkDocs with installation, keyword reference, examples, HIL qualification,
  and release notes.
- PyCharm/Robot Framework setup guide for Windows and Linux.
- Hardware qualification guide (VISA backend setup per OS and per interface: GPIB card
  drivers, USBTMC, LAN/VXI-11 or HiSLIP as applicable).
- At least 10 Robot examples; target 14, matching `rf_keysight_n6700`/`rf_ngi_n83624`.
- Generated Libdoc HTML keyword reference.
- `ai/ai_contract.yaml` + `ai/ai_contract.lock` (RFDS-017), built with the RFDS-002
  canonical keywords as first-class capabilities from the start, not retrofitted.
- History and implementation review for v26.01.

## 16. Scripts

Provide PowerShell, BAT where practical, and Bash scripts for: virtual environment setup,
full test run, individual example run, offline (simulator) example run, wheel/sdist build.
Scripts shall fail fast and use the repository-local `.venv`.

## 17. CI and release checks

GitHub Actions shall test Windows and Linux with supported Python versions and run:

1. editable install;
2. Python unit tests;
3. Robot acceptance tests (simulator);
4. Ruff/mypy static analysis;
5. wheel and sdist build;
6. Robot result artifact upload;
7. AI-contract lock verification (RFDS-017).

GitHub Pages workflow shall build and deploy MkDocs from `main`.

## 18. Acceptance criteria

The task is complete only when:

- [ ] Required package naming and root structure are satisfied.
- [ ] No `src/` layout is used.
- [ ] At least 10 Robot examples exist.
- [ ] RFDS-002 canonical connection keywords are the primary, documented connection API.
- [ ] Output, pulse, modulation, sweep (including markers), burst, front-panel lock,
      arbitrary-waveform, and setup save/restore keywords exist.
- [ ] `Configure Output` never leaves the output enabled as an undocumented side effect.
- [ ] `Enable Output`/`Disable Output` are the sole explicit means of changing output state.
- [ ] Amplitude/offset validation rejects out-of-range combinations before any device I/O.
- [ ] Function-limit "Settings conflict" adjustments are surfaced as typed errors, not
      silently swallowed.
- [ ] Raw SCPI requires exact confirmation text; calibration is only reachable through it.
- [ ] Python tests pass.
- [ ] Robot acceptance tests pass against the simulator.
- [ ] Offline examples pass.
- [ ] Static analysis passes.
- [ ] Wheel and source distributions build.
- [ ] README, Pages, guides, task, history, and review are present.
- [ ] `ai/ai_contract.yaml`/`ai_contract.lock` present and passing.
- [ ] Real 33220A HIL qualification is complete, including the §14.3 cross-interface and
      overvoltage-behavior checks.

The final unchecked item is a deployment qualification gate, not an offline
software-generation defect. The release must remain labeled "hardware qualification
required" until it is completed.

## 19. Open questions for Gate 1 (need confirmation before core implementation)

1. **VISA backend coverage** — confirm `pyvisa`/`pyvisa-py` (or a vendor VISA install)
   actually reaches all three interfaces (GPIB, USB, LAN) in the target test environment
   before relying on the single-backend design in §5.1; GPIB in particular usually needs a
   real GPIB interface card or USB-GPIB adapter with its own driver, independent of pyvisa.
2. **External overvoltage protection behavior** — confirmed to exist and auto-disable
   output (§2/§6 item 3), but the exact error code/message text was not extracted from this
   manual pass; capture the literal `SYSTem:ERRor?` string during Gate 2/hardware testing
   so `Agilent33220ADeviceError` messages can quote it precisely instead of paraphrasing.
3. **LXI/LAN discovery** — the manual confirms LXI Class C compliance but this task doc does
   not specify an mDNS/LXI-discovery keyword; decide during Gate 1 whether bench discovery
   is in scope for v26.01 or deferred (recommendation: defer — `resource` can always be
   supplied explicitly, matching every other VISA-based driver in this repository).
