# Robot Framework Driver Task: Elektro-Automatik EA-PS 9000 T Series DC Laboratory Power Supply

**Status:** Gate 1 — Architecture & Skeleton task document (RFDS-020). No code has been
written yet. This document follows the structure of the three prior task documents in
this repository (`rf_tbs1000c/task/`, `rf_agilent33220a/task/`, `rf_agilent34411a/task/`).

## 1. Objective

Implement `rf_ea_ps9000t`, a Robot Framework driver for the Elektro-Automatik EA-PS 9000 T
series DC laboratory power supply (source-only bench supply, "Tower" mechanical form
factor — abbreviated **PST** throughout this document's source material), following this
repository's two-layer architecture (hardware-agnostic core driver + thin Robot Framework
adapter) and RFDS-001 through RFDS-020.

The PS 9000 T is a wide-range, single-quadrant (source-only, not bidirectional) DC power
supply: constant-voltage/constant-current/constant-power regulation, adjustable
overvoltage/overcurrent/overpower protection thresholds, remote sensing, and a SCPI/ModBus
digital interface over USB, RS232, or Ethernet (all standard; no plug-in Anybus module
needed for those three). **This is a single-model, feature-scoped driver**: the source
material (a family programming guide covering ~13 device series) explicitly confirms, via
its own per-series compatibility tables, that this specific series does **not** support:
sink/bidirectional operation, internal resistance simulation, supervision-feature alarms
(UVD/UCD/OVD/OCD/OPD), master-slave operation, the function/sequence generator, MPP
tracking, PV simulation, the battery-test function, or presets/recall (`*SAV`/`*RCL`).
None of those are implemented by this driver — see §2 for the evidence trail, so a future
maintainer never has to re-derive why a seemingly-standard EA command is absent here.

## 2. Instrument facts (sources: EA Elektro-Automatik / Intepro Systems "Programming Guide
ModBus & SCPI For USB, GPIB, Ethernet and AnyBus modules", Doc ID PGMBEN, Revision 17,
09-18-2019 — covers firmware KE 3.06 for this series, abbreviation **PST**; and
"PS 9000 T Series" Operating Guide, Doc ID PS9TEN, Revision 03, 10/2022. Both read
directly during Gate 1 research; every command and compatibility claim below was checked
against the programming guide's own per-command compatibility table for the **PST**
column specifically — nothing here is inferred from a different series' behavior.)

- **Model identity:** product-key decoding confirmed as `PS <max V><max A>-<max A> T`,
  e.g. `PS 9080-60 T` = 0...80 V, 0...60 A, 0...1500 W (max V and max A are each encoded
  in the model number; rated power is the product, per the family's naming convention,
  not independently encoded). Real cataloged models from the operating guide's validity
  table: PS 9040-20 T, PS 9080-10 T, PS 9200-04 T, PS 9040-40 T, PS 9080-20 T,
  PS 9200-10 T, PS 9040-40 T, PS 9080-40 T, PS 9200-15 T, PS 9500-06 T, PS 9040-60 T,
  PS 9080-60 T, PS 9200-25 T, PS 9500-10 T. This driver is model-agnostic (queries
  nominal values from the connected unit, per §8) rather than hardcoding any one model's
  ratings.
- **Remote interfaces:** USB, RS232, and Ethernet are standard; GPIB/CAN/CANopen/
  Profibus/Profinet/EtherCAT require an optional plug-in Anybus interface module and are
  **out of scope** for this driver (RFDS-005: no dependency on optional hardware for the
  primary transport). Both SCPI and ModBus RTU/TCP protocols are supported on USB/RS232/
  Ethernet simultaneously — the first byte of a message disambiguates them (`0x00` means
  ModBus RTU); this driver is **SCPI-only**, matching every other driver in this
  repository (ModBus is a distinct, unimplemented transport, not a fallback).
  Default Ethernet SCPI/ModBus-RTU-over-TCP port: **5025**. ModBus TCP (a distinct
  framing) is reserved to port 502 and not used by this driver. Default device IP:
  `198.168.0.2` (verbatim from the source document — note this is *not* a typo-correction
  opportunity for this task doc; it is quoted exactly as printed in the manual and must
  be re-verified against real hardware before being relied upon, since `198.168.0.2` is
  outside the private `192.168.0.0/16` block and could be a manual typo for
  `192.168.0.2` — flagged as an open question, §17 item 1).
- **SCPI syntax (§5.2 of the programming guide):** upper case by default (lower case also
  accepted); every command has a long form and short form (e.g. `SOURce`/`SOUR`,
  interchangeable); up to 5 commands may be coupled in one message separated by `;`,
  processed left-to-right; colon separates keyword levels; optional parts in
  `[brackets]`; termination character is optional over USB but **required over
  Ethernet since a specific KE firmware version** (`0x0A` / LF) — this driver always
  sends LF termination unconditionally, since sending it is universally accepted even
  where not required, avoiding a firmware-version-conditional code path. Errors are
  **not** returned automatically after a command — they must be explicitly queried
  (`SYSTem:ERRor?` family) or inferred by polling the status byte's `err` bit; this
  driver follows the same "check after write" pattern already used by every other
  driver in this repository (`_check_events`-style helper).
- **Error codes (§5.2.5):** `0,"No error"`; `-100,"Command unknown"`;
  `-102,"Syntax error"`; `-108,"Parameter not allowed"`; `-200,"Execution error"`;
  `-201,"Invalid while in local"`; `-220,"Parameter error"`;
  `-221,"Settings conflict"`; `-222,"Data out of range"`; `-223,"Too much data"`;
  `-224,"Illegal parameter value"`; `-999,"Safety OVP"` (only on specific 60V-class
  models with the "Safety OVP" hardware feature — requires a power cycle to clear,
  confirmed unerasable from the error queue by any SCPI command).
- **Remote-control activation is mandatory and explicit, unlike every other driver in
  this repository so far.** Unlike the Agilent/Keysight instruments already implemented,
  this device **never accepts a value-changing command until remote control is
  explicitly activated**, and it **never activates automatically** — connecting the
  transport is not enough. The command is `SYSTem:LOCK ON` (equivalently `SYSTem:LOCK 1`)
  to acquire remote control, `SYSTem:LOCK OFF` (`SYSTem:LOCK 0`) to release it back to
  manual/front-panel control, and `SYSTem:LOCK:OWNer?` to query who currently holds it
  (`REMOTE`/`NONE`/`LOCAL`). Remote control can be refused by the device (front panel in
  "Local" lock condition, already remote-controlled via a different interface, or the
  front-panel setup menu is open) — refusal surfaces as a SCPI error, not a silent
  no-op. This is the single most important behavioral difference from every prior
  driver in this repository and drives task §6 item 1 and §7's connection-keyword
  design.
- **Standard IEEE commands (§5.4.1, universal — no per-series compatibility table shown,
  confirmed "supported in all devices which feature SCPI"):** `*CLS` (clears error queue
  and status byte), `*IDN?` (manufacturer, model, serial, firmware version(s), optional
  user text — 5 comma-separated fields, one more than the typical 4-field `*IDN?` this
  repository's other drivers parse, because of the trailing user-text field — see §7),
  `*RST` (switches to remote control, sets DC output off, clears alarm buffer, clears
  status registers — but does **not** relinquish remote control, unlike a bare
  power-cycle), `*STB?` (status byte, bits: 2=`err`, 3=`ques`, 7=`oper`; bits 0/1/4/5/6
  unused on this family).
- **Status registers (§5.4.2, universal):** a two-register model, `STATus:QUEStionable`
  (alarm-style conditions: OVP/OCP/OPP/OT/OVD/UVD/OCD/UCD/OPD, plus Local/Remote/
  Output-on/Function/Power-fail/MSS bits) and `STATus:OPERation` (regulation-mode bits:
  CV/CC/CP/CR/Source-Sink), each with `:CONDition?` (current snapshot), `:EVENt?`
  (latched positive-transition history, cleared on read), and `:ENABle`/`:ENABle?`
  (bitmask filter into the STB summary bits). Device alarms (OVP/OCP/OPP/OT) surface in
  `STATus:QUEStionable` and must be acknowledged via `SYSTem:ERRor?`/`:ERRor:ALL?` —
  reading the error queue **is** the acknowledgment; an alarm not yet acknowledged this
  way cannot be distinguished from one that's still active. The overtemperature (OT)
  condition is the one exception: it self-clears from `CONDition` once the over-temp
  state itself is gone, without requiring acknowledgment.
- **Set value commands (task §8), confirmed applicable to PST (no `SINK:`/`RESistance`
  variants — those are PSB-9000-only bidirectional-device features, confirmed absent for
  PST in the compatibility table):**
  - `[SOURce:]VOLTage[?] <NRf>[Unit]` — 0...1.02× nominal voltage, or `MIN`/`MAX`.
  - `[SOURce:]CURRent[?] <NRf>[Unit]` — 0...1.02× nominal current, or `MIN`/`MAX`.
  - `[SOURce:]POWer[?] <NRf>[Unit]` — 0...1.02× nominal power, or `MIN`/`MAX`.
  - No `[SOURce:]RESistance` (internal-resistance simulation) — confirmed absent from
    PST's compatibility row; do not implement.
- **Protective features (task §8/§9), confirmed present for PST:**
  `[SOURce:]VOLTage:PROTection[:LEVel][?] <NRf>[Unit]` (OVP threshold, 0...1.1×/1.03×
  nominal voltage depending on series — PST uses the 1.1× family), `[SOURce:]CURRent:
  PROTection[:LEVel][?]` (OCP, 0...1.1× nominal current), `[SOURce:]POWer:PROTection
  [:LEVel][?]` (OPP, 0...1.1× nominal power). Thresholds are compared against the
  live input/output value and trip a DC-output shutdown; if the protection threshold is
  set equal to the working set value, protection has priority over regulation (the
  device switches off rather than merely limiting).
- **Measuring (readback) commands (task §8, universal):** `MEASure[:SCALar]:VOLTage
  [:DC]?`, `:CURRent[:DC]?`, `:POWer[:DC]?` (each 0...125% of nominal, decimal places
  matching the front-panel display, varies by model), and `MEASure[:SCALar]:ARRay?`
  (all three values in one comma-separated response, `V, A, W` order).
- **Status/output commands (task §7/§8, PST confirmed):** `OUTPut[?] {ON|OFF}` (DC output
  on/off — PST has an output, confirmed present; the guide's `INPut` command is for
  electronic loads only and is **not** applicable here, confirmed absent for PST),
  `SYSTem:LOCK[?] {ON|OFF|1|0}` / `SYSTem:LOCK:OWNer?` (remote-control acquire/release/
  query, per above), `SYSTem:ERRor?` / `:ERRor:NEXT?` / `:ERRor:ALL?` (FIFO error queue,
  up to 5 concatenated on `:ALL?`).
- **Alarm counters (§5.4.15.3, universal, no acknowledgment needed to read, cleared only
  by power-cycle):** `SYSTem:ALARm:COUNt:OVOLtage?`, `:OTEMperature?`, `:OPOWer?`,
  `:OCURrent?`, `:PFAil?` (all applicable to PST; `:SHARebusfail?`/`:FLOatovp?` are
  10000-series-only, confirmed absent for PST).
- **Adjustment limits (task §11, "Limits" in the front-panel setup menu — narrows the
  standard 0...100%(+2% overrange) adjustment range, e.g. to prevent accidentally
  setting too high a voltage for a connected load; confirmed present for PST for
  voltage/current/power, absent for resistance since PST has no resistance feature):**
  `[SOURce:]VOLTage:LIMit:LOW[?]` / `:HIGH[?]`, `[SOURce:]CURRent:LIMit:LOW[?]` /
  `:HIGH[?]`, `[SOURce:]POWer:LIMit:HIGH[?]` (no `:LOW` variant for power — matches the
  compatibility table exactly, which lists only `POWer:LIMit:HIGH`, not `:LOW`).
  Sending a set value (§ above) that would fall outside the currently configured
  adjustment limit is rejected by the device with a SCPI error (`-222,"Data out of
  range"`), not silently clamped — a real device-side behavior this driver's own
  client-side validation must not attempt to duplicate or second-guess, since the
  limits are themselves runtime-configurable and this driver has no way to
  independently know the current limit values except by querying them.
- **General queries (task §8, universal for the nominal-value trio, resistance variants
  confirmed absent for PST):** `SYSTem:NOMinal:VOLTage?`, `:CURRent?`, `:POWer?` (rated
  values for the connected unit — the correct way for this driver to discover a
  connected unit's actual ratings rather than hardcoding any one model's numbers, per
  §1), `SYSTem:DEVice:CLASs?` (device-class code identifying source/load/charger — this
  driver should read and expose it but not gate behavior on it, since this task targets
  the PST series specifically and doesn't need to distinguish itself from other classes
  at runtime).
- **Device configuration (task §9, PST-applicable subset only, confirmed per-command
  against the compatibility table — several device-configuration commands in the family
  guide are confirmed **absent** for PST and are explicitly excluded below):**
  - `POWer:STAGe:AFTer:REMote[?] {AUTO|OFF}` — DC output state after leaving remote
    control (`AUTO` = last condition persists, `OFF` = always off). Confirmed present.
  - `SYSTem:CONFig:OUTPut:RESTore[?] {AUTO|OFF}` — DC output state after power-on
    (`AUTO` = restores the condition at last power-off, `OFF` = always starts off).
    Confirmed present (the guide lists a combined `INPut:RESTore`/`OUTPut:RESTore` pair
    for load/source devices respectively; PST uses the `OUTPut:` form only).
  - `SYSTem:CONFig:USER:TEXT[?] <SRD>` — up to 40-character user-definable text,
    permanently stored, appears as the 5th field of `*IDN?`. Confirmed present.
  - `SYSTem:COMMunicate:PROTocol:MODBus[?] {ENABLE|DISABLE}` — disables ModBus so only
    SCPI is accepted (only one of the two protocols may be disabled, never both).
    Confirmed present; this driver does not call it (leaves both protocols enabled,
    since disabling ModBus is a standing device-configuration change with no benefit to
    a SCPI-only driver — task §6 item 4).
  - `SYSTem:COMMunicate:TIMeout[?] {5...65535}` — inter-byte fragmentation timeout in
    milliseconds, **serial interfaces only** (USB, RS232 — not meaningful over
    Ethernet). Confirmed present.
  - `SYSTem:ALARm:ACTion:PFail[?] {AUTO|OFF}` / `:OTEMperature[?] {AUTO|OFF}` — DC
    output state after a power-fail or overtemperature alarm clears. Confirmed present
    for PST for both.
  - Ethernet interface configuration (`SYSTem:COMMunicate:LAN:ADDRess`, `:DHCP`,
    `:GATeway`, `:SMASk`, `:HOSTname`, `:DOMain`, `:DNS1`/`:DNS2`, `:KEEPalive`,
    `:TIMeout`, `:MAC?`) — universal across the family (no PST-specific exclusion
    found), but **out of scope for this driver's Gate 2 keyword surface**: these are
    standing network-configuration changes analogous to changing a device's static IP
    from software, which this repository's convention (see `rf_agilent33220a`/
    `rf_agilent34411a`, neither of which exposes LAN-configuration keywords either) does
    not wrap as ordinary measurement/control keywords. Available via the raw SCPI
    escape hatch (§12) if genuinely needed.
  - **Confirmed absent for PST** (found in the family guide but excluded from PST's
    compatibility column — do not implement): `[SOURce:]VOLTage:CONTrol:SPEed`
    (electronic-load-only fast/slow regulator mode), `SYSTem:CONFig:ANAlog:MONitor`,
    `SYSTem:CONFig:ANAlog:PIN6`, `:PIN14`, `:PIN15` (analog-interface alarm/status pin
    remapping — PST's analog interface pinout doesn't support remapping these),
    `SYSTem:CONFig:MODE {UIP|UIR}` (U/I/R mode select — resistance-mode devices only).
    `SYSTem:CONFig:ANAlog:REFerence` and `:REMSB:LEVel`/`:REMSB:ACTion` **are** confirmed
    present for PST but are analog-interface-only settings with no SCPI-remote-control
    relevance (the analog interface is a separate, simultaneous control path via
    physical pins, not something this driver's SCPI session interacts with) — excluded
    from this driver's keyword surface for the same "not an ordinary measurement/control
    keyword" reason as the LAN settings above.
- **Presets/recall — confirmed absent for PST.** `*SAV {1...9}` / `*RCL {1...9}` /
  `MEMory:STATe:DELete` / `MEMory:STATe:VALid?` (a 9-slot save/recall of
  voltage/current/OVP/OCP as a bundle) is confirmed, via the family guide's own
  compatibility table, to be supported **only by the PSI 5000 A series** — not PST. This
  driver therefore has **no setup save/restore keyword at all** (neither host-file, as
  `rf_agilent33220a`/`rf_tbs1000c` implement via a `*LRN?`-equivalent, nor
  instrument-memory-resident, as `rf_agilent34411a` implements via `MEMory:STATe:*`) —
  confirmed as a genuine capability gap in the hardware itself, not a research gap in
  this task document.
- **Function generator, sequence generator, MPP tracking, PV simulation, battery test —
  all confirmed absent for PST**, each via an explicit per-series compatibility table in
  the source document (§5.4.12–§5.4.18) that does not list PST as a supporting series.
  None of these are implemented by this driver.
- **Master-slave operation — confirmed absent for PST**, via the compatibility table for
  §5.4.9. Not implemented.
- **Supervision features (`SYSTem:CONFig:UVD/UCD/OVD/OCD/OPD`, event-triggered
  signal/warning/alarm actions distinct from the hard protection thresholds in §8) —
  confirmed absent for PST**, via the compatibility table for §5.4.7. Not implemented;
  this driver relies solely on the protection thresholds (VOLTage/CURRent/POWer:
  PROTection) already covered above for over-limit handling.
- **Physical/safety facts (operating guide, task §6):**
  - **SELV only below 40 V models; other models generate hazardous DC voltage.** All
    parts under voltage must be covered; work on connections requires zero-voltage
    condition (output disconnected from load) and qualified personnel only.
  - **Never touch DC output terminals directly after switching the output off** —
    residual charge (including from internal X-capacitors) can remain dangerous for a
    period depending on the connected load; this driver documents but cannot enforce
    this (a purely physical hazard, same category as `rf_agilent34411a`'s protection
    limits — no SCPI command exists to poll "is it now safe to touch").
    Never insert a network cable into the master-slave socket on the back of the
    device — physically incompatible and potentially damaging, even though this driver
    doesn't use master-slave itself; worth a docstring note since the connector is
    easily confused with a standard Ethernet port.
  - Interface cards/modules may only be attached/removed with the device switched off —
    not applicable to this driver's runtime behavior (a physical installation
    precaution), but relevant context for anyone wiring an Anybus module for GPIB
    later.
  - "Sense" connector (remote sensing) exists on the front panel for accurate voltage
    regulation at the load, independent of SCPI control — no SCPI command surface
    reads or writes sense-related state directly in the material reviewed; not
    represented as a keyword (nothing to control remotely).

## 3. Mandatory package structure

Mirrors `rf_agilent34411a`/`rf_agilent33220a`/`rf_tbs1000c` (RFDS-005):

```
rf_ea_ps9000t/
├── LICENSE
├── pyproject.toml
├── README.md
├── task/
│   └── ROBOT_FRAMEWORK_DRIVER_TASK_v26.01.md   (this file)
├── ea_ps9000t/                # hardware-agnostic core driver
│   ├── __init__.py
│   ├── exceptions.py
│   ├── enums.py
│   ├── models.py
│   ├── transport.py
│   ├── simulator.py
│   └── driver.py
├── rf_ea_ps9000t/             # Robot Framework adapter
│   ├── __init__.py
│   └── library.py
├── tests/
│   ├── unit/
│   └── robot/
└── examples/
```

## 4. Versioning and packaging

- Python distribution name: `robotframework-ea-ps9000t`.
- Version: `26.1` (matches the Gate 2 baseline convention already used by
  `rf_tbs1000c`/`rf_agilent33220a`/`rf_agilent34411a` in this repository).
- `pyproject.toml` optional dependencies: `visa` (`pyvisa>=1.14`), `visa-py`
  (`pyvisa-py>=0.7`), `dev` (`pytest`, `pytest-cov`, `ruff`, `mypy`, `build`) — same
  shape as the three prior Gate 2 packages, since VISA (USB/Ethernet/RS232, all
  addressable as VISA resource strings) is a workable single transport here too,
  despite EA's own documentation not using VISA terminology (see task §5 for the
  transport design rationale).
- `requires-python = ">=3.10"`, `robotframework>=7.0,<9` core dependency, MIT license.

## 5. Architecture

Two layers, per RFDS-003/RFDS-004:

- **`ea_ps9000t`** — hardware-agnostic core. Owns all SCPI command construction and
  response parsing; the Robot adapter must not duplicate any of this logic.
  - `transport.py`: a `Transport` Protocol, `PyvisaTransport` (lazy `pyvisa` import),
    and `SimulatedTransport` wrapping an in-process `SimEaPs9000TInstrument`. **One
    transport class, not one per interface** — USB, RS232, and Ethernet are all
    addressable as VISA resource strings (`USB0::...`, `ASRL...::INSTR`,
    `TCPIP0::<ip>::5025::SOCKET`), matching the single-VISA-backend precedent already
    established for `rf_agilent33220a`/`rf_agilent34411a`. Unlike SCPI-native
    instruments, this device also speaks ModBus RTU on the same physical port,
    disambiguated by a leading `0x00` byte — this driver never sends that byte, so it
    is unconditionally speaking SCPI; no protocol-detection logic is needed on the
    driver side.
  - `enums.py`: `_ScpiEnum(str, Enum)` base with the same generic case-insensitive
    prefix-matching `_missing_` hook already proven three times in this repository —
    reuse verbatim. Concrete enums: `RemoteLockState` (`ON`/`OFF` — note this is a
    request/release action, not a 3-state readback; `SYSTem:LOCK:OWNer?` returns a
    *different* vocabulary, `REMOTE`/`NONE`/`LOCAL`, modeled as a separate
    `RemoteControlOwner` enum since conflating the two would blur a real semantic
    difference between "what I'm asking for" and "who currently holds it"),
    `PowerStageAfterRemote` (`AUTO`/`OFF`), `OutputRestoreMode` (`AUTO`/`OFF`),
    `AlarmAction` (`AUTO`/`OFF`).
  - `models.py`: `InstrumentIdentity` (5-field — manufacturer/model/serial/firmware/
    user_text, one more field than the 4-field `*IDN?` this repository's other drivers
    parse; see task §7), `NominalRatings` (voltage/current/power), `MeasuredValues`
    (voltage/current/power from `MEASure:ARRay?`), `ProtectionThresholds` (OVP/OCP/OPP),
    `AdjustmentLimits` (voltage/current low+high, power high-only — matching the
    real asymmetric command set confirmed in task §2, not a guessed symmetric shape),
    `AlarmCounters` (OVP/OT/OPP/OCP/PF counts), `ConnectionState` (RFDS-002 §12.1
    shape, `as_dict()`).
  - `simulator.py`: `SimEaPs9000TInstrument`, dict-based `_ROUTES` dispatcher (same
    proven pattern as the three prior drivers). No `;`/`:` concatenated-command replay
    is needed (no `*LRN?`/setup-restore feature exists for this series, confirmed
    absent per task §2) — same simplification already applied to
    `rf_agilent34411a`'s simulator for the analogous reason.
  - `driver.py`: `EaPs9000T` class — connection lifecycle **with explicit remote-lock
    acquire/release** (task §6 item 1), set values (voltage/current/power), protection
    thresholds, measuring/readback, adjustment limits, alarm counters, device
    configuration (the PST-applicable subset from task §2), raw SCPI escape hatch.
- **`rf_ea_ps9000t`** — Robot Framework adapter (`EaPs9000TLibrary`). RFDS-002 canonical
  keywords as the primary API — **with `Connect` additionally acquiring remote control
  and `Disconnect` additionally releasing it**, since on this instrument family
  "connected" and "in remote control" are two genuinely different states and conflating
  them would leave the device refusing every value-changing command after a bare
  `Connect` (task §6 item 1, task §7). Multi-alias session management, a
  `_connection_state(alias, driver)` helper, and a `_robot_value()` dataclass/enum-to-
  dict converter — identical implementation to the pattern already proven three times.

## 6. Signal-integrity and safety requirements

1. **Remote control must be explicitly acquired, and `Connect` must fail loudly if the
   device refuses it — never silently proceed as if commands will work.** Unlike every
   prior driver in this repository, this instrument requires an explicit
   `SYSTem:LOCK ON` before any value-changing command is honored, and the request can be
   refused (front panel in "Local" lock, already remote-controlled elsewhere, or the
   setup menu is open) — refusal surfaces as a SCPI error on the *next* command, not on
   the lock request itself (per task §2's syntax note that SCPI errors are never
   returned automatically). This driver's `Connect` must therefore explicitly query
   `SYSTem:LOCK:OWNer?` after requesting `SYSTem:LOCK ON` and raise a typed
   `EaPs9000TConnectionError` naming the actual owner if it isn't `REMOTE` — silently
   trusting the write to have succeeded would produce a driver that "connects
   successfully" and then mysteriously fails every subsequent `Set Voltage`/`Set
   Current` call with a generic device error, with no clue why.
2. **`Disconnect` releases remote control (`SYSTem:LOCK OFF`) before closing the
   transport**, so the instrument reverts to front-panel-operable state rather than
   being left in a "remote-locked, nobody's listening" condition after a script ends —
   this matters more here than for the source instruments already implemented, since a
   bench power supply left remote-locked is a real inconvenience for the next person at
   the bench, not just an abstract state-hygiene concern.
3. **Never expose Save/Restore Setup keywords.** Confirmed absent for this series
   (task §2) — a maintainer reusing the `rf_agilent33220a`/`rf_agilent34411a` keyword
   list as a template must not carry this one over.
4. **Never disable ModBus** (`SYSTem:COMMunicate:PROTocol:MODBus DISABLE`) from this
   driver. It's a standing, persisted device-configuration change with no benefit to a
   SCPI-only driver and a real cost to anyone else who later wants to use ModBus against
   the same unit — available only through the raw SCPI escape hatch (§12), which
   documents that it bypasses this guard.
5. **Protection thresholds are not client-side-duplicated.** `Set Voltage`/`Set
   Current`/`Set Power` do not attempt to validate against the currently configured
   `LIMit:LOW`/`:HIGH` adjustment range client-side, because this driver has no reliable
   way to know the current limits except by querying them fresh on every set call
   (limits are independently, concurrently adjustable from the front panel per task
   §2's own "special characteristics of remote control" note) — the device's own
   `-222,"Data out of range"` error is the correct and only source of truth here,
   surfaced as a typed `EaPs9000TDeviceError` via the standard post-write error check,
   not pre-empted by a client-side guess that could be stale the moment it's computed.
6. **`*IDN?` is a 5-field response on this family, not the usual 4.** Any code that
   assumes a 4-field split (as every prior driver in this repository correctly does for
   *their* instruments) will silently drop or mis-parse the trailing user-text field
   here — `identify()` must split on exactly 5 fields (comma-limited to 4 splits) and
   treat a missing 5th field (empty user text is common) as an empty string, not an
   error.

## 7. Required connection keywords (RFDS-002 canonical, primary API)

Same set and semantics as the three prior drivers, **plus explicit remote-control
handling per task §6 items 1–2**: `Connect(resource=None, alias="default",
timeout_s=None, **options)` (VISA resource string, or `resource=None` +
`options[simulated]=True`) — acquires remote control as part of connecting and raises a
typed error if refused, → RFDS-002 §12.1 connection-state dictionary;
`Disconnect(alias=None)` — releases remote control before closing, idempotent;
`Is Connected(alias=None)` → bool, never raises for a missing session;
`Get Connection State(alias=None, refresh=False)`; `Check Communication(alias=None)`
(issues `*IDN?`); `Get Identity(alias=None, refresh=True)` (5-field parse, task §6
item 6); `Get Remote Control Owner(alias=None)` (wraps `SYSTem:LOCK:OWNer?` — a keyword
unique to this driver among the four in this repository, since no prior instrument had a
queryable "who owns remote control" concept worth exposing); `Switch Power Supply`/
`Get Active Power Supply`/`List Power Supply Connections` for multi-alias sessions.

## 8. Set value, measuring, and general-query keywords

- **Set values:** `Set Voltage`/`Get Voltage`, `Set Current`/`Get Current`,
  `Set Power`/`Get Power` — no resistance variant (task §2).
- **Protection thresholds:** `Set Overvoltage Protection`/`Get Overvoltage Protection`,
  `Set Overcurrent Protection`/`Get Overcurrent Protection`, `Set Overpower Protection`/
  `Get Overpower Protection`.
- **Output control:** `Enable Output`/`Disable Output`/`Is Output Enabled`
  (`OUTPut ON`/`OFF`/`OUTPut?`).
- **Measuring:** `Get Measured Voltage`, `Get Measured Current`, `Get Measured Power`,
  `Get Measured Values` (the `MEASure:ARRay?` triple as one dataclass).
- **General queries:** `Get Nominal Voltage`, `Get Nominal Current`, `Get Nominal Power`
  (the correct way to discover a connected unit's actual ratings, task §2), `Get Device
  Class`.
- **Alarm counters:** `Get Alarm Counters` → one dataclass with OVP/OT/OPP/OCP/PF counts
  (task §2; the 10000-series-only counters are not included since this driver targets
  PST specifically).

## 9. Adjustment limits and device configuration keywords

- **Adjustment limits (task §2, asymmetric — no power `:LOW`):**
  `Set Voltage Limit Low`/`Set Voltage Limit High`/`Get Voltage Limits`,
  `Set Current Limit Low`/`Set Current Limit High`/`Get Current Limits`,
  `Set Power Limit High`/`Get Power Limit High` (no `Set Power Limit Low` — matches the
  real asymmetric command set, not a guessed symmetric one).
- **Device configuration (PST-applicable subset only, task §2):**
  `Set Power Stage After Remote`/`Get Power Stage After Remote`,
  `Set Output Restore Mode`/`Get Output Restore Mode`, `Set User Text`/`Get User Text`,
  `Set Communication Timeout`/`Get Communication Timeout` (serial interfaces only —
  docstring notes this, doesn't hard-fail over Ethernet since the device itself will
  simply ignore or error on the setting rather than this driver needing to pre-empt
  it), `Set Power Fail Alarm Action`/`Get Power Fail Alarm Action`,
  `Set Overtemperature Alarm Action`/`Get Overtemperature Alarm Action`.
- **Explicitly not included** (task §2/§6 item 4): ModBus enable/disable, LAN
  configuration, analog-interface configuration, `VOLTage:CONTrol:SPEed`,
  `SYSTem:CONFig:MODE`.

## 10. Raw SCPI escape hatch

- `Enable Raw SCPI` requires the exact confirmation string `"ENABLE RAW SCPI"`
  (matching every other driver in this repository).
- `Raw SCPI Query`/`Raw SCPI Write` document that they bypass typed validation — this is
  also the sanctioned path to ModBus-disable, LAN configuration, and analog-interface
  configuration (task §2/§9), deliberately not wrapped as typed keywords.

## 11. Simulator requirements

The bundled simulator shall support, deterministically and without hardware:

- `*IDN?` (5-field, including a settable user-text field), `*CLS`, `*RST`, `*STB?`.
- **Remote-control state machine**, task §6 item 1's core behavior: `SYSTem:LOCK
  {ON|OFF}` and `SYSTem:LOCK:OWNer?`, with a test hook to force a refusal (simulate
  "Local" lock condition or "already remote-controlled elsewhere") so the driver's
  "query owner after requesting lock, raise if not REMOTE" behavior (task §6 item 1) is
  genuinely exercised offline, not just assumed to work.
- Set value state (voltage/current/power) and protection-threshold state (OVP/OCP/OPP),
  each read back what was set; a test hook to make the simulator reject an out-of-limit
  set value with `-222,"Data out of range"` so this driver's "surface the device's own
  error, don't pre-empt it" behavior (task §6 item 5) is genuinely exercised.
- Output on/off state (`OUTPut`), read back what was set; commands issued while remote
  control is not held must be rejected with `-201,"Invalid while in local"`, matching
  real device behavior and exercising this driver's post-write error-check path.
- Adjustment-limit state (voltage/current low+high, power high-only) — read back what
  was set.
- Measuring commands returning a deterministic, settable value per quantity (same
  "configurable next reading" pattern as `rf_agilent34411a`'s simulator).
- Device configuration state (power-stage-after-remote, output-restore, user text,
  communication timeout, power-fail/overtemperature alarm actions) — read back what was
  set.
- Alarm counters as simple incrementing integers with a test hook to trigger each one.
- `SYSTem:ERRor?`/`:ERRor:ALL?` FIFO error queue (up to 5 entries), matching the pattern
  already proven three times in this repository.
- `SYSTem:NOMinal:VOLTage?`/`:CURRent?`/`:POWer?`/`SYSTem:DEVice:CLASs?` returning fixed,
  documented simulated values.

## 12. Tests

### 12.1 Python unit tests

Cover at minimum:

1. Simulator connect and identity (5-field `*IDN?` parse, including a populated user-text
   field and an empty one).
2. `Connect` acquires remote control and raises a typed `EaPs9000TConnectionError` naming
   the actual owner when the simulator is forced to refuse the lock request (task §6
   item 1) — the core safety-relevant behavior test for this driver.
3. `Disconnect` releases remote control before closing (task §6 item 2) — verify
   `SYSTem:LOCK:OWNer?` reads back `NONE` after disconnecting, via a session that stays
   open on the simulator side long enough to check (or via a transport-level hook).
4. Set voltage/current/power and protection-threshold round-trips.
5. A simulated `-222,"Data out of range"` on a set-value write surfaces as a typed
   `EaPs9000TDeviceError`, not silently swallowed, and this driver never attempts to
   pre-validate against the adjustment limits client-side (task §6 item 5) — assert no
   limit-query call happens before the set-value write.
6. Output enable/disable/is-enabled round-trip; a command issued while remote control is
   not held raises a typed error reflecting the device's own `-201,"Invalid while in
   local"` response.
7. Adjustment limits round-trip, including the asymmetric power-limit shape (no
   `Set Power Limit Low` keyword exists at all — a `pytest` check that the method/keyword
   genuinely doesn't exist, not just that it's untested).
8. Device configuration round-trips (power-stage-after-remote, output-restore, user
   text, alarm actions).
9. Alarm counters read back correctly after the simulator's trigger hooks are used.
10. Raw SCPI guard (rejects without exact confirmation text).
11. Robot data-conversion helpers (dataclass/enum → dict/scalar).
12. Multi-alias session handling.
13. `Set Communication Timeout` — confirm it's implemented as a plain pass-through
    keyword (no client-side interface-type gating), since the driver has no reliable way
    to know at the SCPI layer whether the active transport is serial or Ethernet.

### 12.2 Robot acceptance tests

Must run offline against the simulator and cover: identity, connect/disconnect lifecycle
(including remote-control acquisition and release, and the RFDS-002 generic keywords),
set voltage/current/power and an immediate measurement via `Get Measured Values`,
overvoltage/overcurrent/overpower protection threshold configuration, output enable/
disable, adjustment limits, and at least one device-configuration round trip.

### 12.3 Hardware tests (RFDS-019 conformance)

Create a marked hardware test plan; do not run automatically in CI. Include, against a
real PS 9000 T unit:

- identity and firmware capture over USB, RS232, and Ethernet at least once each, to
  confirm the single-VISA-backend design (§5) genuinely works across all three;
- confirm remote-control refusal behavior with the front panel deliberately left in
  "Local" lock condition, and confirm the driver's typed error correctly names the
  actual owner;
- confirm the `-222,"Data out of range"` device-side rejection at the actual configured
  adjustment-limit boundary, cross-checked against the front-panel-displayed limit
  values;
- confirm the `198.168.0.2` default-IP question from task §17 item 1 against the actual
  factory-default IP printed on a real unit's label or setup menu;
- confirm `-999,"Safety OVP"` behavior (60V-class models only, if available on the test
  bench) requires an actual power cycle to clear, not just `*CLS`/`SYSTem:ERRor?`.

## 13. Documentation and examples

- `README.md` following the house style established by the three prior drivers: title +
  version + Gate status, install (with `[visa,visa-py]` extras), a runnable Robot
  Framework quick-start example against the simulator, a full keyword list grouped by
  section, and a safety-relevant-behaviors section (remote-control acquisition/release,
  no client-side limit duplication, no setup save/restore — and why not, per task §2).
- `examples/`: at minimum an identify-and-remote-control suite (demonstrating explicit
  lock acquisition, including what a refusal looks like), a set-value-and-measure suite,
  a protection-threshold suite, and an adjustment-limits suite.
- `ai/ai_contract.yaml`-equivalent (RFDS-017) is Gate 4 work, not Gate 2 — do not create
  it yet. Per this repository's established (RFDS-017-deviating) convention, name it
  `ea_ps9000t_ai_contract.yaml`/`.lock` when that work starts.

## 14. Scripts

None required for Gate 1/Gate 2, matching the precedent of the three prior drivers.

## 15. CI and release checks

Deferred to Gate 4/5 per RFDS-020 — not in scope for this task document.

## 16. Acceptance criteria

Gate 2 (Core Implementation) is complete when:

- [ ] Core driver (`ea_ps9000t`) implements connection lifecycle **with explicit
  remote-control acquire/release** (§6, §7), set values/protection/measuring/general
  queries (§8), adjustment limits/device configuration (§9), and the raw SCPI escape
  hatch (§10), each backed by the bundled simulator.
- [ ] Robot Framework adapter (`rf_ea_ps9000t`) wraps every implemented core method as a
  keyword, with RFDS-002 canonical connection keywords (extended per §6/§7) as the
  primary API.
- [ ] Unit tests (§12.1) and Robot acceptance tests (§12.2) pass; `ruff`/`mypy`/`build`
  are clean.
- [ ] README and examples (§13) are complete for everything actually implemented.
- [ ] No keyword exists for any feature confirmed absent for PST in §2 (sink/resistance
  mode, supervision features, master-slave, function/sequence generator, MPP tracking,
  PV simulation, battery test, presets/recall) — a maintainer template-copying from
  `rf_agilent33220a`/`rf_agilent34411a` must not have carried over a keyword that
  doesn't apply to this hardware.
- [ ] The single open question in §17 that could affect real-hardware connectivity (the
  default-IP transcription question) is flagged in the README's hardware-connection
  section, not silently assumed correct.

## 17. Open questions for Gate 1

This task document was grounded directly in the EA/Intepro Systems "Programming Guide
ModBus & SCPI" (Doc ID PGMBEN, Rev. 17) and the "PS 9000 T Series" Operating Guide (Doc ID
PS9TEN, Rev. 03) — both read in full for every section relevant to this driver's scope,
and every command/compatibility claim in §2 was checked against the guide's own per-series
compatibility table for the PST column. Only one genuinely open item remains:

1. **Default Ethernet IP address transcription.** §2.7 of the programming guide states
   the default IP as `198.168.0.2`, which is outside the private `192.168.0.0/16` range
   and is very plausibly a manual typo for `192.168.0.2` (a common default in this
   product family based on general networking convention, though not independently
   confirmed elsewhere in the material reviewed). This driver does not hardcode this
   value anywhere in code (connection always takes an explicit `resource` string from
   the caller, per RFDS-002), so it does not block any keyword — but the README's
   hardware-connection guidance should quote the value exactly as printed and flag the
   discrepancy for a user connecting to a factory-default unit for the first time,
   rather than silently "correcting" it to `192.168.0.2` without hardware to confirm
   against.
