# Keyword Guide

## Connections

- `Open N83624 TCP Connection`
- `Open N83624 UDP Connection`
- `Open N83624 Channel UDP Connection`
- `Open N83624 Serial Connection`
- `Open N83624 Emulator`
- `Switch N83624 Connection`
- `Close N83624 Connection`
- `Close All N83624 Connections`

## Safety and output

- `Set Channel Safety Limits`
- `Arm Channel Output`
- `Disarm Channel Output`
- `Enable Channel Output`
- `Disable Channel Output`
- `All N83624 Outputs Off`

Output arming requires exact text `ENABLE OUTPUT`. Any limit change disarms the affected channel.

## Operating modes

- `Set Channel Mode`
- `Configure Source Mode`
- `Configure Charge Mode`
- `Configure SOC Profile`
- `Configure Sequence Profile`

SOC and sequence steps accept Robot lists of dictionaries or JSON lists.

## Measurements and assertions

- `Measure Channel Voltage`
- `Measure Channel Current`
- `Measure Channel Power`
- `Measure Channel Resistance`
- `Measure Channel Capacity`
- `Measure Channel`
- `Measure Voltage Channels`
- `Channel Voltage Should Be Within`
- `Channel Current Should Be Within`
- `Wait Until Channel Voltage Is Within`
- `Wait Until Channel Current Is Within`

## Diagnostics

- `Start N83624 Heartbeat`
- `Get N83624 Communication Health`
- `Recover N83624 Connection`
- `Enable Raw SCPI`
- `Raw SCPI Query`
- `Raw SCPI Write`
- `Export Diagnostic Bundle`

Raw SCPI bypasses typed validation and is disabled unless explicitly enabled.
`Export Diagnostic Bundle` zips the calling alias's RFDS-008 evidence run —
see [Logging and Evidence](logging-and-evidence.md).
