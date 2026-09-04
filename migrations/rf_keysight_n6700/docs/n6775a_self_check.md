# N6775A Full Self-Check

## Purpose

`tests/conformance/driver_call_protocol_conformance.robot` is the real-device RFDS-019 self-check for a Keysight N6775A installed in an N6700-family mainframe. It validates the complete public Robot library surface against the N6775A profile:

- every one of the 63 exported keywords is inventoried;
- 45 applicable/local keywords have protocol or callability vectors;
- 18 alternative-connection, SMU, or electronic-load calls are explicitly excluded for this profile;
- unsupported SMU/load calls are still invoked and must fail before transmission;
- applicable SCPI commands are checked by read-back, schema, error-queue, or recovery oracles;
- all transport writes, queries, responses, errors, and durations are captured in JSONL.

This is a command/protocol self-check. It does not replace calibration or independent electrical-accuracy verification.

## Safety defaults

The default run is non-energizing:

- `HIL_ENABLE` is required for physical hardware;
- output is forced OFF during setup, after each test, and during suite teardown;
- `ALLOW_RESET` defaults to false;
- `ALLOW_ACTIVE_OUTPUT` defaults to false;
- test defaults are 1.0 V, 0.10 A, and 2.0 V OVP;
- test values are rejected when they exceed the configured 60 V, 5 A, or 300 W module limits;
- teardown restores configuration values but intentionally leaves the tested output OFF.

Use `-AllowActiveOutput` only with reviewed wiring, a safe load/open-circuit fixture, current limiting, interlocks, and an emergency-disconnect procedure.

## Windows PowerShell

USB resource configured for this N6775A:

```powershell
.\scripts\run_n6775a_self_check.ps1 `
  -Resource "USB0::0x0957::0x0907::MY43014421::INSTR" `
  -ConnectionType usb `
  -Channel 1
```

Because this USB address is the packaged default, the following also uses it:

```powershell
.\scripts\run_n6775a_self_check.ps1
```

LAN VISA resource:

```powershell
.\scripts\run_n6775a_self_check.ps1 `
  -Resource "TCPIP0::192.168.0.50::inst0::INSTR" `
  -ConnectionType visa `
  -Channel 1
```

Raw SCPI socket:

```powershell
.\scripts\run_n6775a_self_check.ps1 `
  -Resource "192.168.0.50" `
  -ConnectionType ethernet `
  -Port 5025 `
  -Channel 1
```

Enable reset vector:

```powershell
.\scripts\run_n6775a_self_check.ps1 -Resource "TCPIP0::192.168.0.50::inst0::INSTR" -AllowReset
```

Enable the guarded active-output vector:

```powershell
.\scripts\run_n6775a_self_check.ps1 -Resource "TCPIP0::192.168.0.50::inst0::INSTR" -AllowActiveOutput
```

## Windows CMD

```bat
set N6700_RESOURCE=USB0::0x0957::0x0907::MY43014421::INSTR
set N6700_CONNECTION_TYPE=usb
set N6700_CHANNEL=1
scripts\run_n6775a_self_check.bat
```

## Linux/macOS

```bash
N6700_RESOURCE='USB0::0x0957::0x0907::MY43014421::INSTR' \
N6700_CONNECTION_TYPE=usb \
N6700_CHANNEL=1 \
./scripts/run_n6775a_self_check.sh
```

## Software-only syntax and simulator smoke profile

The simulator does not model N6775A by default, so the runner selects its installed power-supply model when `ConnectionType=simulated`. This confirms suite callability and evidence generation, but is not N6775A hardware acceptance.

```powershell
.\scripts\run_n6775a_self_check.ps1 -ConnectionType simulated
```

## Test groups

1. Session selection and aliases.
2. Mainframe identity and exact N6775A channel discovery.
3. Common SCPI response formats.
4. Instrument self-test.
5. Status clear, wait, and error queue.
6. Voltage set/query round-trip.
7. Current-limit set/query round-trip.
8. Combined safe PSU configuration.
9. Output-OFF command family and read-back.
10. OVP and OCP round-trip.
11. Measurement response schemas.
12. Measurement assertions and polling.
13. Protection status and safe clear.
14. Invalid SCPI error and communication recovery.
15. Pre-transmission argument validation.
16. Correct rejection of SMU and electronic-load APIs.
17. Optional reset/recovery.
18. Optional active-output/read-back.
19. All-channel safe shutdown.
20. Disconnect/reconnect recovery.
21. Required SCPI command/response trace families.

## Evidence

Each runner creates:

```text
results/call_protocol_conformance/keysight_n6700/<timestamp>/
├── output.xml
├── log.html
├── report.html
├── conformance_summary.md
├── keyword_inventory.json
├── keyword_coverage.csv
├── protocol_vector_results.json
├── protocol_trace.jsonl
├── protocol_trace.log
├── outbound_trace.log
├── inbound_trace.log
├── environment.json
├── device_identity.json
└── exclusions.json
```

The Robot exit code is preserved. A failed mandatory vector makes the runner fail. Optional reset/active-output vectors remain visible as `SKIP` unless enabled.

## Static conformance validation

```bash
python scripts/validate_call_protocol_conformance.py
```

This verifies that all 63 public keywords are represented by exactly one protocol vector or approved exclusion and that every vector references an existing Robot test.

## Command-line boolean handling

Release v26.05 normalizes `HIL_ENABLE`, `ALLOW_RESET`, and `ALLOW_ACTIVE_OUTPUT` with Robot Framework's `Convert To Boolean` before evaluating guards. This prevents lowercase runner values such as `true` or `false` from becoming invalid Python expressions such as `not true`.

A result showing `NameError: name 'true' is not defined` was produced by the v26.04 test harness before any instrument connection or SCPI exchange. Upgrade to v26.05 before repeating the hardware run.

## N6700 command forms used by this suite

The OCP vectors use `CURR:PROT:STAT <Bool>,(@ch)` and
`CURR:PROT:STAT? (@ch)`. Protection polling uses
`STAT:QUES:COND? (@ch)`. These forms follow the N6700 command tree and preserve
the mandatory blank between `?` and the channel list.

## Startup error-queue normalization

The dedicated N6775A self-check drains stale SCPI errors and sends `*CLS` before its first strict-checked output command. This prevents errors left by an earlier interrupted run from being misattributed to a valid command. Normal library connections do not clear status unless `clear_errors_on_connect=True` is explicitly requested.

> **N6775A power measurement:** the module does not support direct `MEAS:POW?`. The library reads `MEAS:VOLT?` and `MEAS:CURR?`, calculates watts, and reports `power_source=calculated`.
