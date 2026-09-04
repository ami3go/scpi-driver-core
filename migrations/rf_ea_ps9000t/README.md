# RF EA-PS 9000 T

Robot Framework driver for the Elektro-Automatik EA-PS 9000 T series DC laboratory power
supply (source-only, "Tower" form factor). Version **26.2**. Gate 2 (Core
Implementation, RFDS-020): connection with explicit remote-control acquisition, set
values (voltage/current/power), protection thresholds (OVP/OCP/OPP), output control,
measuring, adjustment limits, alarm counters, and device configuration are all
implemented and tested against the bundled simulator. Gate 3 (Extended Features): LAN
interface identity configuration and analog-interface configuration (reference range,
REM-SB pin behavior) are also implemented. Gate 4 (full docs/AI contract/CI) and Gate 5
(review/release) have not started yet — see `task/` for the driver specification and
readiness review that shaped this implementation.

This is a **single-model, feature-scoped driver**. The source material (a family
programming guide covering ~13 Elektro-Automatik device series) explicitly confirms, via
its own per-series compatibility tables, that this specific series does **not** support
sink/bidirectional operation, internal resistance simulation, supervision-feature
alarms, master-slave operation, the function/sequence generator, MPP tracking, PV
simulation, the battery-test function, or presets/recall. None of those are implemented
here — see `task/ROBOT_FRAMEWORK_DRIVER_TASK_v26.01.md` §2 for the evidence trail.

## Install

From this repository root:

```console
python -m pip install -e "./rf_ea_ps9000t[dev]"
```

Add `pyvisa` (and `pyvisa-py` for a pure-Python VISA backend) to talk to real hardware
over USB, RS232, or Ethernet — all three are standard on this instrument and addressable
as VISA resource strings, so no per-interface extra is needed:

```console
python -m pip install -e "./rf_ea_ps9000t[visa,visa-py]"
```

Run the offline acceptance suite against the bundled simulator — no supply required:

```console
python -m robot --outputdir results rf_ea_ps9000t/tests/robot/acceptance.robot
```

## Robot Framework use

```robotframework
*** Settings ***
Library         rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup     Connect    simulated=${TRUE}
Suite Teardown  Disconnect

*** Test Cases ***
Configure A 24 V 5 A Output
    Set Voltage    24
    Set Current    5
    Enable Output
    ${values}=    Get Measured Values
    Log    Measured: ${values}[voltage] V, ${values}[current] A
    Disable Output
```

Against real hardware, pass a VISA resource string instead of `simulated=${TRUE}`:

```robotframework
Connect    resource=TCPIP0::192.168.0.2::5025::SOCKET
```

Over USB or RS232 the instrument enumerates as a serial port, so use the VISA `ASRL`
resource class with the COM port number (Windows) or device path (Linux/macOS) instead
of the Ethernet form above:

```robotframework
Connect    resource=ASRL5::INSTR
```

For the common case of a plain Windows COM port, `Connect` also accepts the port
number/name directly — either a `com_port` argument or a `resource` shorthand — and
expands it to the `ASRL` form above automatically:

```robotframework
Connect    com_port=5
# or equivalently:
Connect    resource=COM5
```

`Connect` acquires remote control as part of connecting and raises a typed error if the
device refuses it — see Safety notes below.

## Keywords

- **Connection (RFDS-002, extended with remote-control handling):** `Connect`
  (also acquires remote control), `Disconnect` (also releases it), `Is Connected`,
  `Get Connection State`, `Check Communication`, `Get Identity`,
  `Get Remote Control Owner` (`REMOTE`/`NONE`/`LOCAL`), `Switch Power Supply`,
  `Get Active Power Supply`, `List Power Supply Connections`
- **Set values:** `Set/Get Voltage`, `Set/Get Current`, `Set/Get Power` (no resistance
  variant — this instrument doesn't have one)
- **Protection thresholds:** `Set/Get Overvoltage Protection`,
  `Set/Get Overcurrent Protection`, `Set/Get Overpower Protection`,
  `Get Protection Thresholds`
- **Output control:** `Enable Output`, `Disable Output`, `Is Output Enabled`
- **Measuring:** `Get Measured Voltage`, `Get Measured Current`, `Get Measured Power`,
  `Get Measured Values`
- **General queries:** `Get Nominal Ratings` (the correct way to discover a connected
  unit's actual ratings — never hardcode a model's numbers), `Get Device Class`,
  `Get Alarm Counters`
- **Adjustment limits** (asymmetric — no power "low" limit on this instrument family):
  `Set/Get Voltage Limit Low/High`, `Set/Get Current Limit Low/High`,
  `Set Power Limit High`, `Get Power Limit High`, `Get Adjustment Limits`
- **Device configuration:** `Set/Get Power Stage After Remote`,
  `Set/Get Output Restore Mode`, `Set/Get User Text`, `Set/Get Communication Timeout`
  (serial interfaces only), `Set/Get Power Fail Alarm Action`,
  `Set/Get Overtemperature Alarm Action`
- **LAN configuration (Gate 3):** `Set/Get LAN DHCP Enabled`, `Set/Get LAN IP Address`,
  `Set/Get LAN Subnet Mask`, `Set/Get LAN Gateway`, `Set/Get LAN Hostname`,
  `Set/Get LAN Domain`, `Set/Get LAN DNS1`, `Set/Get LAN DNS2`,
  `Set/Get LAN Control Port` (rejects `502`, reserved for ModBus TCP),
  `Set/Get LAN Keepalive Enabled`, `Set/Get LAN Timeout`, `Get LAN MAC Address`
  (read-only). `SYSTem:COMMunicate:LAN:1SPEed`/`:2SPEed`/`:INDex` are deliberately not
  implemented — they describe optional multi-port Anybus/IF-AB Ethernet modules and the
  10000-series dual-port selector, not this driver's PST series' single built-in port.
- **Analog interface configuration (Gate 3):** `Set/Get Analog Reference Range`
  (`5`/`10` volts), `Set/Get Analog REMSB Level` (`NORMAL`/`INVERTED`),
  `Set/Get Analog REMSB Action` (`OFF`/`AUTO`)
- **Raw SCPI escape hatch:** `Enable Raw SCPI` (requires the exact confirmation text
  `"ENABLE RAW SCPI"`), `Raw SCPI Query`, `Raw SCPI Write` — also the sanctioned path to
  ModBus-disable, which remains deliberately excluded from the typed keyword surface
  (see Safety notes)
- **Diagnostics:** `Export Diagnostic Bundle` — zips the current RFDS-008 evidence run
  (see "Logging and evidence" below) for troubleshooting

Multiple power supplies can be driven from one suite via the `alias` parameter accepted
by every non-connection keyword.

## Safety-relevant behaviors

- **Remote control must be explicitly acquired and can be refused.** Unlike every other
  driver in this repository, this instrument never accepts a value-changing command
  until `SYSTem:LOCK ON` is sent, and it can refuse that request (front panel in "Local"
  lock condition, already remote-controlled via a different interface, or the setup menu
  is open). `Connect` requests the lock and then explicitly re-queries who holds it,
  raising a typed `EaPs9000TConnectionError` naming the actual owner if it isn't
  `REMOTE` — it never trusts the write to have silently succeeded. `Disconnect` releases
  remote control before closing the transport, so the instrument reverts to
  front-panel-operable state.
- **Device-side adjustment limits are the source of truth, never duplicated
  client-side.** `Set Voltage`/`Set Current`/`Set Power` do not pre-validate against the
  currently configured `Limits` range, because those limits are independently,
  concurrently adjustable from the front panel — the device's own `-222,"Data out of
  range"` error is surfaced as a typed `EaPs9000TDeviceError` instead.
- **No setup save/restore keyword exists.** Confirmed absent for this series (presets/
  recall is PSI-5000-A-series-only) — this is a genuine hardware capability gap, not a
  research gap.
- **Never touch DC output terminals directly after switching the output off** — residual
  charge can remain dangerous for a period depending on the connected load. This is a
  purely physical hazard this driver documents but cannot enforce in software.
- **Physical note, unrelated to this driver's own operation:** never insert a network
  cable into the master-slave socket on the back of the device — physically incompatible
  with a standard Ethernet connector and potentially damaging.
- ModBus is never disabled by this driver (`SYSTem:COMMunicate:PROTocol:MODBus`) —
  it's a standing device-configuration change with no benefit to a SCPI-only driver and
  a real cost to anyone else who later wants to use ModBus against the same unit; only
  available through the raw SCPI escape hatch.
- LAN and analog-interface configuration keywords (Gate 3) are ordinary
  device-configuration commands with no special guard beyond the instrument's universal
  remote-control gating — like every mutating keyword on this instrument, they're
  rejected with a typed error if remote control isn't held.
- An `ai/ai_contract.yaml` (RFDS-017 machine-readable contract) has not been generated
  yet; that is Gate 4 work. When it is, this repository's convention names it
  `ea_ps9000t_ai_contract.yaml`/`.lock`.

## Hardware tests

`tests/hardware/verify_all_keywords.robot` exercises every one of this library's public
keywords (KW-001..KW-087, including `Export Diagnostic Bundle`) against a real PS 9000 T
unit and checks its response — one test case per keyword. It is tagged `hardware` and
does not run in CI; run it explicitly:

```console
python -m robot --outputdir results tests/hardware/verify_all_keywords.robot
```

By default it connects over the USB virtual COM port (`COM_PORT`, default `5`) since
that's the only interface most benches expose; override with `-v COM_PORT:<n>`, or pass
`-v RESOURCE:<visa string>` to test over RS232/Ethernet instead. The DC output stays off
for the whole suite unless `-v ALLOW_OUTPUT_ON:True` is passed (only do this with a
suitable load, or nothing, connected), and LAN-identity `Set` keywords
(IP/subnet/gateway/hostname/DNS/...) are read-only unless `-v ALLOW_LAN_WRITES:True` is
passed. Every keyword that mutates device-persistent state (adjustment limits, protection
thresholds, device configuration, LAN/analog settings) restores the original value before
its own test case ends, and Suite Teardown restores the adjustment limits captured at
Suite Setup — the instrument is left as it was found either way. Every keyword call this
suite makes is also recorded as RFDS-008 evidence, including the raw SCPI exchange — see
"Logging and evidence" below — making a full run of this suite a useful real-device SCPI
reference in its own right.

## Logging and evidence

Every keyword call — and every raw SCPI command/response — is recorded as structured,
correlated RFDS-008 evidence, one run per connected `alias`, written to
`results/session/rf_ea_ps9000t/<run>/` (override with the `RFDS_EVIDENCE_ROOT`
environment variable). This is on by default; construct the library with
`evidence_enabled=${FALSE}` to disable it, or call `Export Diagnostic Bundle` to zip the
current run for a bug report. See `docs/logging_and_evidence.md` for the full evidence
layout and `guide/evidence_and_diagnostics.md` for a task-oriented "my test failed, now
what" walkthrough. Validate a run's integrity (hashes, JSONL sequencing) with:

```console
python scripts/validate_evidence.py results/session/rf_ea_ps9000t/<run>/
```

## Running the tests

Unit tests (`tests/unit/`, `tests/evidence/`) run against the bundled protocol-level
simulator — no hardware or `pyvisa` required:

```console
python -m pip install -e ".[dev]"
python -m pytest
```

The offline acceptance suite (`tests/robot/acceptance.robot`) also runs against the
simulator:

```console
python -m robot --outputdir results tests/robot/acceptance.robot
```

`tests/hardware/verify_all_keywords.robot` is the RFDS-019 real-hardware conformance
suite described above and requires a real PS 9000 T unit; it is tagged `hardware` and
does not run in CI.

## Known documentation discrepancy

Confirmed against real hardware (RFDS-019 conformance run): this instrument's firmware
appends a trailing unit suffix to some numeric query responses (e.g.
`SYSTem:NOMinal:VOLTage?` replying `"500.0 V"`) even though the programming guide's
examples and the bundled simulator both show a bare number. Every numeric getter parses
the leading numeric token, so both forms work transparently — nothing to do on the
keyword side, noted here only because the guide doesn't mention it.

The source programming guide states the default Ethernet IP as `198.168.0.2`, which is
outside the private `192.168.0.0/16` range and is very plausibly a manual typo for
`192.168.0.2`. This driver never hardcodes this value (connection always takes an
explicit `resource` string), so it doesn't affect any keyword — but if you're connecting
to a factory-default unit for the first time over Ethernet, verify the actual IP against
the unit's setup menu or label rather than trusting either number blindly.
