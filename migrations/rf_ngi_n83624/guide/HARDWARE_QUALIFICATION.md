# NGI N83624 Hardware Qualification Guide

## Purpose

Qualify `rf-ngi-n83624` against the exact instrument model, firmware, communication interface, fixture, and DUT safety controls. Offline emulator results are necessary but insufficient for production release.

## Required bench equipment

- NGI N83624 under test.
- Independent calibrated DMM or DAQ for voltage/current verification.
- Appropriate load/DUT simulator or protected fixture.
- Emergency stop or rapid power isolation.
- Correct fusing and current-limited upstream supply where applicable.
- Network switch/cable or RS232 interface.
- Host PC with the package installed in a clean `.venv`.

## Evidence header

Record before testing:

- Driver ZIP and Python package versions.
- Git commit/tag if used.
- Python version.
- Robot Framework version.
- OS version.
- Instrument model, serial number, firmware, and `*IDN?` response.
- Interface and connection parameters.
- Fixture revision.
- DMM/DAQ model, serial number, and calibration date.
- Operator and date.

`tests/hardware/verify_all_keywords.robot` (v26.02+) is a fast, safe, automatable
first pass covering keyword-callability and SCPI-protocol conformance for
every public keyword — a useful precursor to Gate H1 below, but not a
replacement for it or for Gates H2-H8.

## Gate H1 — Communication and identity

1. Connect over TCP.
2. Capture `*IDN?` and communication health.
3. Repeat for RS232 when used.
4. Verify UDP only when required.
5. Confirm response terminators and idle timeout behavior.
6. Leave all outputs off.

**Pass:** 100 consecutive identity queries without malformed response or unexplained reconnect.

## Gate H2 — Read-only measurements

For each production-used channel:

1. Confirm output is off.
2. Read voltage, current, power, resistance, capacity, status, and event where applicable.
3. Compare idle readback to independent measurement.
4. Test aggregate selected-channel queries.

**Pass:** No command mapping errors; units and sign conventions documented.

## Gate H3 — Configuration with output off

For source, charge, SOC, and sequence modes used by the bench:

1. Set conservative software limits.
2. Configure mode and setpoints with output disabled.
3. Read back configuration.
4. Confirm no physical output appears during mode change.
5. Verify command names and step/file indexing against hardware.

**Pass:** Every set/readback mapping is confirmed and no unintended output transition occurs.

## Gate H4 — Controlled output enable

Start with a low-risk load and conservative values.

1. Configure finite limits.
2. Configure source mode with output off.
3. Arm the channel.
4. Enable output.
5. Compare voltage/current with independent measurement.
6. Disable output.
7. Verify residual voltage/energy decay.

Repeat across representative low/mid/high setpoints and all used current ranges.

**Pass:** Error is within instrument specification and bench acceptance limits; output-off reaches the defined safe state.

## Gate H5 — Protection

Verify OVP/OCP/OPP behavior using approved procedures that cannot damage the DUT or instrument. Confirm event/status bits and recovery sequence.

## Gate H6 — Exceptional shutdown

At conservative output values, verify:

- normal suite teardown;
- failed Robot test teardown;
- keyboard interrupt;
- host process termination;
- TCP cable removal;
- switch power interruption;
- serial disconnect;
- heartbeat threshold and reconnect;
- one injected channel communication error while other channels are commanded off.

Record whether physical output state is known or unknown after each fault.

## Gate H7 — UDP characterization

When UDP is required:

1. Run packet-loss/duplication/reordering tests.
2. Confirm response association under rapid queries.
3. Confirm per-channel port mapping 7001–7024.
4. Define when TCP is mandatory.

## Gate H8 — Endurance

- 8-hour communication soak with periodic read-only queries.
- 1000 conservative output on/off cycles on a qualified fixture.
- Repeated mode changes with output-off checks.
- Audit-log and Robot-result review for lost responses, retries, state drift, or resource leaks.

## Exit criteria

Production qualification requires:

- All used keywords mapped to hardware evidence.
- No unresolved critical/major finding.
- Safe shutdown behavior documented for every tested fault.
- Limits approved by bench owner.
- Residual risks accepted in writing.
- Qualification evidence referenced in `history/` and `review/` of the next release.
