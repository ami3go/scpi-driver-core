# Task: Robot Framework Driver for Tektronix TBS1000C

**Task revision:** 26.01-draft
**Date:** 2026-08-01
**Target package:** `rf_tbs1000c_v26.01.zip`
**Required internal repository root:** `rf_tbs1000c/`

## 1. Objective

Create a Robot Framework library for the Tektronix TBS1000C series 2-channel digital
storage oscilloscopes (TBS1052C / TBS1072C / TBS1102C / TBS1152C / TBS1202C), built on a
new typed Python core driver (`tbs1000c`) that owns SCPI framing, transport, and waveform
decoding. Unlike the other instruments in this repository, the TBS1000C is a passive
**measurement** instrument — it does not source or sink power into a DUT — so the primary
engineering risk here is measurement integrity and non-destructive defaults, not electrical
hazard.

This package shall build the RFDS-002 canonical connection lifecycle
(`Connect` / `Disconnect` / `Is Connected` / `Get Connection State` / `Check Communication` /
`Get Identity`) as the **primary, documented API** from the outset, matching the pattern
already established in `rf_hp34401a` and `rf_votsch_climate_chamber` — the other six
packages in this repository had these keywords added after the fact and carry both a
generic and an instrument-specific name for the same lifecycle actions. This package should
not repeat that debt: instrument-specific connection keywords (if any) should be a thin
alias over the canonical ones, not a parallel implementation.

The package must support offline verification without hardware and define a separate,
explicit qualification process for the exact TBS1000C model, firmware, and probe set.

## 2. Instrument facts (source: Tektronix TBS1000C Series Programmer Manual, 077-1691-02,
May 2024 — verify against the exact unit's firmware before Gate 2)

- **Transport:** USB only, via USBTMC (USB Test and Measurement Class), on the rear-panel
  USB 2.0 device port. **Confirmed against the official TBS1000C Series datasheet**
  (tek.com): the instrument has no built-in Ethernet/LAN or RS-232, and GPIB is available
  only through the optional Tektronix TEK-USB-488 converter connected to that same USB
  device port — not a native GPIB port. This resolves the programmer manual's generic
  interface table (`GPIB=Yes, RS-232=No, USB=Yes`), which was describing what's reachable
  with the optional adapter, not the instrument's built-in ports. **v26.01 targets USBTMC
  only; TEK-USB-488/GPIB support is explicitly out of scope and would be a separate
  transport backend added later if a bench actually needs it.**
- **Identity formats** (from the manual, both confirmed real, not assumed):
  - `*IDN?` → `TEKTRONIX,<model>,CF:91.1CT FV:v<fw version> TBS 1XXXC:v<module fw version>`
    (IEEE-488.2 standard format; this is what `Get Identity` should parse/return).
  - `ID?` → `ID TEK/<model>,CF:91.1CT FV:v<fw version>` (Tektronix Codes and Formats
    notation; a legacy alternate to `*IDN?`, not needed for this driver).
- **Command grammar:** Tektronix mnemonic-style SCPI (`CH<x>:...`, `TRIGger:A:...`,
  `ACQuire:...`), not strict IEEE-488.2 SCPI-99. Commands and their mnemonic mixed-case
  abbreviations (e.g. `ACQuire` may be sent as `ACQ`) both work; queries append `?`.
- **Command groups relevant to this driver** (see the manual for full argument grammar):
  - `*IDN?`, `*CLS`, `*RST`, `*OPC?`, `*CAL?`, `BUSY?` — standard/common commands.
  - `*ESR?`, `*ESE`, `EVENT?`, `EVMsg?`, `ALLEv?` — standard event-status register and
    error/event queue. `Check Communication` and the `Restore Setup` acceptance check in
    §10.3 both depend on reading this queue, not just on a command completing without a
    transport error.
  - `ACQuire:MODe`, `ACQuire:STATE`, `ACQuire:STOPAfter`, `ACQuire:NUMACq?`,
    `ACQuire:NUMAVg`, `ACQuire:MAXSamplerate?` — acquisition control.
  - `CH<x>:SCAle`, `CH<x>:POSition`, `CH<x>:OFFSet`, `CH<x>:COUPling`, `CH<x>:BANdwidth`,
    `CH<x>:INVert`, `CH<x>:PRObe`, `CH<x>:PRObe:GAIN`, `CH<x>:LABel`, `CH<x>:YUNit` —
    per-channel vertical setup.
  - `TRIGger:A`, `TRIGger:A:EDGE:SOUrce`, `TRIGger:A:EDGE:SLOpe`, `TRIGger:A:EDGE:COUPling`,
    `TRIGger:A SETLevel`, `TRIGger FORCe` — trigger configuration.
  - `AUTOSet`, `AUTOSet:ENABLE` — automatic scale/trigger fit. State-changing and
    surprising if called mid-test; treat as a guarded keyword (see §6).
  - `MEASUrement:IMMed?`, `MEASUrement:ENABLE`, `MEASUrement:GATing`,
    `MEASUrement:CLEARSNapshot` — immediate/on-screen measurements.
  - `CURSor:ENABLE`, `CURSor:FUNCtion`, `CURSor:HBArs:POSITION<x>` — cursor measurements.
  - `DATa:SOUrce`, `DATa:STARt`, `DATa:STOP`, `CURVe?` — waveform record selection and
    transfer.
  - `WFMOutpre?` and its sub-fields (`BIT_Nr`, `BN_Fmt`, `BYT_Nr`, `ENCdg`, `NR_Pt`,
    `XINcr`, `XUNit`, `XZEro`, `YMUlt`, `YOFf`, `YUNit`, `YZEro`) — waveform preamble.
    **These fields are mandatory to convert raw `CURVe?` bytes into real (time, volts)
    pairs; do not hardcode scaling.**
  - `CALibrate:INTERNal:STARt`, `CALibrate:INTERNal:STATus?`, `CALibrate:RESults?` —
    internal self-calibration. Takes the instrument offline for the duration; must be
    explicitly requested, never automatic.
  - `ALIas:DEFine`, `ALIas[:STATE]`, `ALIas:CATalog?` — instrument-side command macros;
    out of scope for v26.01 (raw SCPI escape hatch covers this need if a user wants it).
  - `SAVe:IMAge <path>`, `SAVe:IMAge:FILEFormat {PNG|BMP|JPG}`, `SAVe:IMAge:LAYout
    {LANdscape|PORTRait}` — screen capture. **Writes to the instrument's own filesystem**
    (its internal store or a USB drive in the scope's front-panel port), not to the host.
  - `SAVe:WAVEform[<wfm>,{REF<x>}]|[REF<x>,<QString>]`, `SAVe:WAVEform:FILEFormat
    {INTERNal|SPREADSheet}`, `RECAll:WAVEForm <path>,REF<x>` — instrument-side waveform
    save/recall (`.isf` binary or a spreadsheet/CSV format). Also writes to the
    instrument's own filesystem, not the host.
  - `SAVe:SETUp {<file path>|<NR1>}`, `RECAll:SETUp {FACtory|<NR1>|<file path>}`, `*SAV
    <NR1>`, `*RCL <NR1>` — front-panel setup save/recall, either to one of the instrument's
    10 numbered internal memory slots or to a file path on the instrument's own filesystem.
  - `*LRN?` — standard IEEE-488.2 "learn" query. **Confirmed**: identical to `SET?`, whose
    entry is fully documented — both return "most instrument settings" as a single
    semicolon-delimited, colon-header-concatenated command string that can be resent
    verbatim to restore that state (example from the manual:
    `ACQUIRE:STOPAFTER RUNSTOP;STATE 1;MODE SAMPLE;...:DISPLAY:FORMAT YT;...`). Two
    behaviors to design around, both documented rather than assumed: (1) `SET?`/`*LRN?`
    always return full command headers regardless of the `HEADer` setting, so the response
    is self-describing and safe to resend without tracking `HEADer` state; (2) the `VERBose`
    setting controls whether headers are abbreviated or full-length in that response, which
    is irrelevant to correctness — §2's "Command Entry" grammar already allows either form
    on send, so the driver can treat the returned string as opaque and resend it unchanged
    either way. "Most instrument settings" (the manual's own wording, see Appendix B in the
    source manual for the full factory-setting list) — not guaranteed literally exhaustive;
    document this as a known scope boundary for `Save Setup`/`Restore Setup`, not a hidden
    assumption.
  - `FILESystem:CWD`, `FILESystem:DIR?`, `FILESystem:READFile <path>`,
    `FILESystem:WRITEFile <path>,<data>`, `FILESystem:FREESpace?` — the instrument's file
    system. `READFile` "writes the contents of the specified file to the specified
    interface" — i.e. streams a file's bytes back over the same USBTMC session used for
    every other command. **This is the only documented way to get a `SAVe:IMAge` or
    file-based `SAVe:WAVEform`/`SAVe:SETUp` result onto the host** — there is no direct
    "give me these bytes" query for those three; it's always a two-step
    save-to-instrument-then-read-the-file sequence.

## 3. Mandatory package structure

```text
rf_tbs1000c/
├── rf_tbs1000c/             Robot Framework Python library (adapter)
├── tbs1000c/                new typed core driver: transport, SCPI, waveform decode
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

1. ZIP filename shall be `rf_tbs1000c_v26.01.zip`.
2. ZIP shall contain exactly one top-level folder named `rf_tbs1000c`.
3. Human-facing release label shall be `v26.01`.
4. Python distribution version shall be PEP 440-compatible `26.1`.
5. Distribution name: `robotframework-tbs1000c` (matches the `robotframework-<name>`
   convention used by `rf_bk8500b` and `rf_keysight_n6700`, both VISA/USBTMC instruments).
6. The Python import shall be `rf_tbs1000c`.
7. The primary Robot import shall be:

```robot
Library    rf_tbs1000c.Tbs1000cLibrary
```

## 5. Architecture

### 5.1 Layers

1. **Robot Framework layer** — keyword names, Robot-friendly argument conversion,
   assertions, RFDS-002 connection-state dictionary, cleanup.
2. **Typed Python driver layer** (`tbs1000c`) — SCPI formatting/parsing, channel/trigger/
   acquisition models, waveform preamble decoding, enums, validation.
3. **Transport layer** — USBTMC via `pyvisa` (VISA resource string, e.g.
   `USB0::0x0699::0x03C4::<serial>::INSTR`), plus a deterministic in-process simulator.
   No GPIB/serial/Ethernet backend in v26.01 per §2.
4. **Instrument layer** — the physical TBS1000C, probes, and DUT under observation.

### 5.2 Design constraints

- Robot keywords shall not duplicate SCPI formatting logic; that belongs in `tbs1000c`.
- Waveform scaling (raw codes → volts/seconds) shall always be derived from a fresh
  `WFMOutpre?` read taken with (or immediately around) the `CURVe?` transfer it applies
  to — never from a cached/assumed preamble, since scale/position changes invalidate it.
- Returned dataclasses/enums shall convert to Robot dictionaries, lists, strings, booleans,
  integers, or floats.
- Raw SCPI shall be an explicitly guarded escape hatch, consistent with every other driver
  in this repository (RFDS-006 §19 prohibits silent duplicate protocol construction).
- Exceptions shall follow RFDS-007: a `Tbs1000cError`-rooted hierarchy
  (`Tbs1000cConnectionError`, `Tbs1000cTimeoutError`, `Tbs1000cProtocolError`,
  `Tbs1000cValidationError`, `Tbs1000cDeviceError`, ...), not bare built-ins raised at the
  keyword boundary.
- Every "save X to a file" keyword that touches the instrument's own filesystem
  (screen image, instrument-side waveform export, file-based setup save) shares one
  driver-layer helper that performs `SAVe:... <instrument path>` then
  `FILESystem:READFile <instrument path>` and writes the returned bytes to the **host**
  path the caller asked for — implement this once in `tbs1000c`, not per keyword.

### 5.3 Host-side configuration profile (RFDS-014, `config/`)

Unlike a power supply or load, this instrument has no meaningful "default output limits" to
persist — its config profile is a small, host-side connection/behavior default, not a device
safety envelope. `config/schema.json` (Draft 2020-12, `additionalProperties: false`) defines:

```json
{
  "resource": "USB0::0x0699::0x03C4::<serial>::INSTR",
  "timeout_s": 5.0,
  "default_image_format": "png",
  "default_channel_labels": {"CH1": null, "CH2": null}
}
```

- `resource` — optional; when present, lets `Connect` default `resource` from a profile
  instead of a hardcoded suite value. `null`/absent means "must be supplied by the caller or
  the simulator is used," matching the RFDS-002 `Connect` contract already specified in §7.
- `timeout_s` — optional default applied when `Connect`'s `timeout_s` argument is omitted.
- `default_image_format` — one of `png`/`bmp`/`jpg`; default for `Save Screen Image` when
  its `image_format` argument is omitted.
- `default_channel_labels` — optional; if set, applied via `Set Channel Name` right after a
  successful `Connect`, purely as host-side convenience (the instrument itself does not
  persist a "default" label across power cycles beyond whatever `CH<x>:LABel` last set).
  `null` entries are left as whatever the instrument currently reports.
- `config/schema.lock`, `config/default.json`, `config/example.json` follow the same
  convention as every other package in this repository (RFDS-014 §"canonical interchange").
  No secrets, credentials, or device-write-on-load semantics apply — loading a profile never
  contacts the instrument by itself; it only supplies defaults for keyword arguments.

## 6. Measurement-integrity requirements

This instrument has no output to energize, so "safety" here means: don't silently corrupt
or misrepresent a capture.

1. `AUTOSet` changes vertical scale, trigger level, and timebase without asking — it shall
   be logged at `INFO` with the settings before and after, and shall never run implicitly
   from `Connect`.
2. `CALibrate:INTERNal:STARt` takes the instrument offline for the duration of the
   calibration; it shall never run automatically, and any keyword called while a
   calibration is in progress (`CALibrate:INTERNal:STATus?`) shall fail clearly rather than
   time out silently.
3. Waveform transfer keywords shall reject a `CURVe?` result whose byte count doesn't match
   `WFMOutpre:NR_Pt?` / `WFMOutpre:RECOrdlength?` rather than returning a truncated or
   misaligned trace.
4. `Get Immediate Measurement`-style keywords shall raise a typed error (not return a
   fabricated or clipped value) for `MEASUrement:IMMed?` results that read back
   `∞`/`-∞`/out-of-range codes — mirroring the "reject overload rather than fabricate" rule
   already established for `rf_hp34401a`.
5. `Trigger Force` and any other keyword that can end an in-progress acquisition shall be
   named so its effect is unambiguous in a Robot log, not buried inside a getter.
6. Channel probe attenuation (`CH<x>:PRObe:GAIN`) must be set correctly for scaled
   measurement keywords to report true DUT values — document this loudly; the driver cannot
   detect a physically-mismatched probe.

## 7. Required connection keywords (RFDS-002 canonical, primary API)

- `Connect(resource=None, alias="default", timeout_s=None, **options)` → RFDS-002 §12.1
  connection-state dictionary. `resource` is the USB VISA resource string; omit for the
  bundled simulator (`resource=None` + `options[simulated]=True`).
- `Disconnect(alias=None)` — idempotent.
- `Is Connected(alias=None)` → bool, never raises for a missing session.
- `Get Connection State(alias=None, refresh=False)` → RFDS-002 §12.1 dictionary.
- `Check Communication(alias=None)` → bool, raises on failure (issues `*IDN?` or `BUSY?`).
- `Get Identity(alias=None, refresh=True)` → stable identity string from `*IDN?`.
- `Switch Oscilloscope` / `Get Active Oscilloscope` / `List Oscilloscope Connections` — only
  if multi-alias sessions are implemented (recommended, matching every other multi-instrument
  package in this repository).

No instrument-specific `Connect To ...` keyword is required; if one is added for
readability, it shall be a documented alias that calls `Connect` internally, not a second
implementation.

## 8. Channel, trigger, and acquisition keywords

- `Set/Get Channel Scale`, `Set/Get Channel Position`, `Set/Get Channel Offset`
- `Set/Get Channel Coupling`, `Set/Get Channel Bandwidth Limit`, `Set/Get Channel Probe Gain`
- `Set/Get Channel Name(channel, name=None)` → `CH<x>:LABel`. `name` is a free-text label
  (e.g. `"ICCDATA"`) shown on the instrument display and in waveform metadata — purely
  cosmetic, no electrical effect. Validate and reject before sending rather than let the
  instrument silently truncate: max 30 characters per the manual; empty string clears the
  label (`CH<x>:LABel?` returns `""` when unset).
- `Enable/Disable Channel Display` (`CH<x>:INVert`/on-off equivalents as available)
- `Set/Get Trigger Source`, `Set/Get Trigger Slope`, `Set/Get Trigger Level`,
  `Set/Get Trigger Coupling`
- `Force Trigger`
- `Run Autoset` (guarded per §6 item 1)
- `Start/Stop Acquisition`, `Set Acquisition Mode` (sample / average / peak-detect),
  `Get Acquisition Count`
- `Run Internal Calibration`, `Get Calibration Status`, `Get Calibration Results` (guarded
  per §6 item 2)

## 9. Measurement and waveform keywords

- `Get Immediate Measurement` — supported types, from `MEASUrement:IMMed:TYPe`'s argument
  grammar: `AMPlitude`, `AREa`, `BURst`, `CARea`, `CMEan`, `CRMs`, `DELay`, `FALL`,
  `FREQuency`, `HIGH`, `LOW`, `MAXimum`, `MEAN`, `MINImum`, `NDUty`, `NEDGECount`,
  `NOVershoot`, `NPULSECount`, `NWIdth`, `PEDGECount`, `PDUty`, `PERIod`, `PHAse`, `PK2Pk`,
  `POVershoot`, `PPULSECount`, `PWIdth`, `RISe`, `RMS`. Map these to a Robot-friendly enum
  rather than passing the mnemonic straight through.
- `Measurement Should Be Within` (assertion helper, mirrors the pattern in every other
  package's `... Should Be Within` keywords)
- `Get Waveform` → dictionary with decoded `time_s` / `volts` arrays (or a compact encoded
  form Robot can consume) plus the full preamble (`x_increment`, `x_zero`, `y_multiplier`,
  `y_offset`, `y_zero`, `unit`, `record_length`) so callers can re-derive values themselves.
  This is the **primary** waveform path: `CURVe?` + `WFMOutpre?` decoded on the host, with
  no dependency on the instrument having any local storage.

## 10. File-transfer keywords: screen capture, waveform export, and setup save/restore

These three feature areas share the two-step instrument-file → `FILESystem:READFile` →
host-file mechanism from §2/§5.2, except for setup save/restore's primary path, which
avoids it entirely via `*LRN?`.

### 10.1 Save screen image

- `Save Screen Image(path, image_format=None, layout=None)` → saves the current display to
  a **host** file at `path`. Behavior: pick an instrument-side temp filename (extension
  matching `image_format`, default inferred from `path`'s suffix — `png`/`bmp`/`jpg`), set
  `SAVe:IMAge:FILEFormat` and optionally `SAVe:IMAge:LAYout`, issue `SAVe:IMAge`, then read
  the file back with the shared file-transfer helper and write it to `path` on the host.
  Delete the instrument-side temp file afterward on a best-effort basis so repeated calls
  don't fill the instrument's storage.
- Document that a screen capture reflects whatever is currently displayed — if the
  acquisition is running, that's a live view, not a frozen record; pair with
  `Stop Acquisition` first if a caller needs the image to match a specific captured trace.

### 10.2 Save waveform to CSV

- `Save Waveform To CSV(path, channel, alias=None)` → calls the §9 `Get Waveform` host-side
  decode path and writes `time_s,volts` rows to `path` on the host. This is the primary
  implementation; it does not touch the instrument's filesystem and works identically
  against the simulator.
- `Save Waveform To CSV On Instrument(path, channel, alias=None)` (optional, vendor-native
  alternate) → sets `SAVe:WAVEform:FILEFormat SPREADSheet`, issues
  `SAVe:WAVEform CH<x>, <instrument path>`, then uses the shared file-transfer helper to
  pull that file to the host `path`. Document why it exists (matches what the instrument's
  own front-panel "Save Waveform" produces, useful for cross-checking the driver's own CSV
  writer) and that §9's `Get Waveform` is the keyword everything else in this driver
  (assertions, evidence capture) should build on.

### 10.3 Save and restore instrument setup

- `Save Setup(path, alias=None)` → issue `*LRN?`, write the returned string verbatim to a
  host text file at `path`. No instrument-side file involved. Confirmed design per §2: the
  response is a single self-describing, resend-ready command string.
- `Restore Setup(path, alias=None)` → read `path` from the host and send its contents back
  to the instrument as one concatenated command. Verify the instrument accepts it (check
  `*ESR?`/`EVENT?`/`EVMsg?` after — see §2) rather than assuming success; a malformed or
  foreign file should fail this check, not silently reconfigure the instrument (§13.1
  item 13).
- `Save Setup To Instrument Memory(slot, alias=None)` / `Restore Setup From Instrument
  Memory(slot, alias=None)` (optional, vendor-native alternate) → thin wrappers over `*SAV
  <NR1>` / `*RCL <NR1>` for the instrument's 10 numbered internal slots; useful for a
  known-good front-panel state a user has already saved by hand, no file involved at all.
- `Restore Factory Setup(alias=None)` → `RECAll:SETUp FACtory`.
- `*LRN?`'s response format is now confirmed from the manual (§2), so `Save Setup`/
  `Restore Setup` can be implemented as designed at Gate 2, not as a stub. The residual risk
  is ordinary firmware-accuracy risk, not a design unknown: §13.3 still requires confirming
  a real captured `*LRN?` response actually round-trips on physical hardware before this
  feature is considered hardware-qualified, and "most instrument settings" (the manual's own
  phrasing) should be treated as a documented scope boundary — some obscure setting could
  turn out not to be covered — not as a guarantee of literal completeness. If real-hardware
  testing contradicts the documented behavior, fall back to `SAVe:SETUp <instrument path>` +
  the shared file-transfer helper as the primary path instead, and update this section.

## 11. Raw SCPI escape hatch

- `Enable Raw SCPI` shall require an exact confirmation string, matching the
  `rf_ngi_n83624`/`rf_eresistor` pattern (e.g. `ENABLE RAW SCPI`).
- `Raw SCPI Query` / `Raw SCPI Write` shall document that they bypass typed validation and
  waveform-preamble consistency checks.

## 12. Simulator requirements

The bundled simulator shall support, deterministically and without hardware:

- `*IDN?`, `*CLS`, `BUSY?`
- Channel scale/position/coupling/probe state (read back what was set)
- A synthetic trigger and acquisition state machine (run/stop/single)
- A synthetic waveform (e.g. a generated sine or square wave) with a real, consistent
  `WFMOutpre?` preamble, so waveform-decode logic can be unit-tested against known values
- Injected/deterministic immediate-measurement results
- A minimal in-memory filesystem backing `SAVe:IMAge`/`SAVe:WAVEform`/`SAVe:SETUp` +
  `FILESystem:READFile`, so §10's file-transfer keywords are exercised end-to-end offline
  (a real PNG/BMP encoder isn't required — a small deterministic placeholder image is
  enough to prove the two-step save-then-read mechanism works)
- A deterministic `*LRN?` response (e.g. a fixed, versioned settings string) so
  `Save Setup`/`Restore Setup` round-trip in tests without real firmware

## 13. Tests

### 13.1 Python unit tests

Cover at minimum:

1. Simulator connect and identity.
2. Waveform decode: known raw bytes + known preamble → known (time, volts) arrays,
   including at least one binary and one ASCII encoding case.
3. Byte-count mismatch between `CURVe?` and the preamble raises, not truncates.
4. Overload/out-of-range measurement values raise rather than return a number.
5. `AUTOSet` and `CALibrate:INTERNal:STARt` are never called implicitly by `Connect`.
6. Raw SCPI guard (rejects without exact confirmation text).
7. Robot data-conversion helpers (dataclass/enum → dict/scalar).
8. Multi-alias session handling, if implemented.
9. `Set Channel Name` rejects a label over 30 characters before sending anything to the
   instrument, and an empty string round-trips as `Get Channel Name` returning `""`.
10. `Save Screen Image` writes the exact bytes the simulator's `FILESystem:READFile`
    returned to the requested host path, and cleans up the instrument-side temp file.
11. `Save Waveform To CSV` produces a CSV whose rows match the decoded `Get Waveform`
    arrays exactly.
12. `Save Setup` → `Restore Setup` round-trips against the simulator's deterministic
    `*LRN?` response.
13. A `Restore Setup` call with a corrupted/foreign file content fails clearly instead of
    silently reconfiguring the instrument with garbage.

### 13.2 Robot acceptance tests

Must run offline against the simulator and cover: identity, connect/disconnect lifecycle
(including the RFDS-002 generic keywords), channel setup including channel naming, trigger
setup, run/stop acquisition, an immediate measurement, a full waveform fetch-and-decode, a
screen-image save, a waveform-to-CSV save, and a setup save/restore round trip.

### 13.3 Hardware tests (RFDS-019 conformance)

Create a marked hardware test plan; do not run automatically in CI. Include, against a real
TBS1000C unit and probes:

- identity and firmware capture;
- channel scale/position/coupling readback verification;
- trigger on a known reference signal;
- waveform fetch cross-checked against an independent measurement (e.g. a calibrated
  function generator amplitude);
- probe-gain mismatch behavior (documented, not silently "fixed" by the driver);
- internal calibration start/status/result cycle;
- USB disconnect/reconnect recovery behavior;
- a real `*LRN?` response captured and diffed against the manual's documented shape (§2) —
  confirms the design rather than discovering it; trigger the §10.3 fallback only if this
  disagrees with the documented behavior;
- a real screen-image save opened and visually verified, for at least one of PNG/BMP/JPG;
- a setup saved on real hardware, instrument power-cycled or reset, then restored from the
  saved file and readback-verified against the original configuration.

## 14. Documentation and examples

Deliver, matching every other package in this repository:

- README with install, import, quick start, safety/measurement-integrity notes, examples,
  test/build commands, layout, and status.
- GitHub Pages / MkDocs with installation, keyword reference, examples, HIL qualification,
  and release notes.
- PyCharm/Robot Framework setup guide for Windows and Linux.
- Hardware qualification guide (probe compensation, USBTMC driver setup per OS).
- At least 10 Robot examples; target 14, matching `rf_keysight_n6700`/`rf_ngi_n83624`.
- Generated Libdoc HTML keyword reference.
- `ai/ai_contract.yaml` + `ai/ai_contract.lock` (RFDS-017), built with the RFDS-002
  canonical keywords as first-class capabilities from the start, not retrofitted.
- History and implementation review for v26.01.

## 15. Scripts

Provide PowerShell, BAT where practical, and Bash scripts for: virtual environment setup,
full test run, individual example run, offline (simulator) example run, wheel/sdist build.
Scripts shall fail fast and use the repository-local `.venv`.

## 16. CI and release checks

GitHub Actions shall test Windows and Linux with supported Python versions and run:

1. editable install;
2. Python unit tests;
3. Robot acceptance tests (simulator);
4. Ruff/mypy static analysis;
5. wheel and sdist build;
6. Robot result artifact upload;
7. AI-contract lock verification (RFDS-017).

GitHub Pages workflow shall build and deploy MkDocs from `main`.

## 17. Acceptance criteria

The task is complete only when:

- [ ] Required package naming and root structure are satisfied.
- [ ] No `src/` layout is used.
- [ ] At least 10 Robot examples exist.
- [ ] RFDS-002 canonical connection keywords are the primary, documented connection API.
- [ ] Channel, trigger, acquisition, measurement, and waveform-transfer keywords exist.
- [ ] Waveform decode is derived from a live preamble read, never a cached/assumed one.
- [ ] Overload/invalid measurement results raise rather than return fabricated values.
- [ ] `AUTOSet` and internal calibration are explicit, guarded, and never implicit.
- [ ] `Save Screen Image` writes a valid host-side image file via the two-step
      save-then-`FILESystem:READFile` mechanism, and cleans up its instrument-side temp file.
- [ ] `Save Waveform To CSV` produces a host-side CSV via the host-decoded `Get Waveform`
      path, matching the decoded waveform exactly.
- [ ] `Save Setup` / `Restore Setup` round-trip a configuration through a host file, with
      the `*LRN?`-vs-`SAVe:SETUp` mechanism decision resolved and documented per §10.3.
- [ ] Raw SCPI requires exact confirmation text.
- [ ] Python tests pass.
- [ ] Robot acceptance tests pass against the simulator.
- [ ] Offline examples pass.
- [ ] Static analysis passes.
- [ ] Wheel and source distributions build.
- [ ] README, Pages, guides, task, history, and review are present.
- [ ] `ai/ai_contract.yaml`/`ai_contract.lock` present and passing.
- [ ] Real TBS1000C HIL qualification is complete, including the §13.3 `*LRN?`
      characterization, screen-capture visual check, and setup round-trip on real hardware.

The final unchecked item is a deployment qualification gate, not an offline
software-generation defect. The release must remain labeled "hardware qualification
required" until it is completed.

## 18. Open questions for Gate 1 (need confirmation before core implementation)

1. ~~GPIB support~~ — resolved against the official TBS1000C datasheet (see §2): no native
   GPIB port; only reachable via the optional TEK-USB-488 converter. Explicitly out of
   scope for v26.01 (§2, §5.1).
2. **Exact model(s) in scope** — TBS1052C/1072C/1102C/1152C/1202C share a command set but
   differ in bandwidth/sample rate; confirm the specific unit(s) this driver targets for
   hardware qualification. **Still open** — no amount of manual research resolves this; it's
   a decision for whoever owns the physical bench inventory.
3. ~~Measurement type enumeration~~ — resolved; see §9. The list above comes directly from
   the `MEASUrement:IMMed:TYPe` argument grammar in the programmer manual and needs no
   further research before Gate 2.
4. **USBTMC driver setup per OS** — Windows typically needs Tektronix's TekVISA or a
   NI-VISA/pyvisa-py backend; Linux needs `usbtmc` kernel module or `libusb` permissions.
   Document exactly which combination Gate 4's hardware guide will assume. **Still open** —
   a documentation-writing task for Gate 4, not a design blocker for Gate 2.
5. ~~`*LRN?` response format~~ — resolved; see §2 and §10.3. `*LRN?` is documented as
   identical to the fully-specified `SET?` query: a single semicolon-delimited, self-
   describing command string. Design proceeds as specified; only real-firmware
   confirmation (§13.3) remains, which is ordinary hardware qualification, not an open
   design question.

Of the five original items, three are now resolved from documentation research alone. The
remaining two (exact model selection, per-OS driver setup instructions) are not research
gaps — they're a bench-ownership decision and a Gate 4 documentation task respectively, and
neither blocks starting Gate 2 core implementation.
