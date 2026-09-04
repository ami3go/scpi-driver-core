# Status and Protection

## Manual-defined OCP commands

For N6700 source modules such as the N6775A, over-current protection is
controlled through the full `PROTection:STATe` node:

```text
CURR:PROT:STAT ON,(@1)
CURR:PROT:STAT OFF,(@1)
CURR:PROT:STAT? (@1)
```

`CURR:PROT` is the protection subsystem, not a complete command. The shorter
forms `CURR:PROT ON` and `CURR:PROT?` are not valid abbreviations because the
mandatory `STATe` header is omitted.

## Live protection status

The N6700 does not define a generic `OUTP:PROT?` query. Read the live,
non-latched Questionable Condition register for the selected channel:

```text
STAT:QUES:COND? (@1)
```

The driver decodes these relevant bits:

| Bit | Value | Meaning | Driver field |
|---:|---:|---|---|
| 0 | 1 | Positive over-voltage protection | `over_voltage` |
| 1 | 2 | Over-current protection | `over_current` |
| 2 | 4 | Power fail | `power_fail` |
| 3 | 8 | Positive power limit/protection | `power_limit` |
| 4 | 16 | Over-temperature protection | `over_temperature` |
| 5 | 32 | Negative power limit/protection | `power_limit` |
| 6 | 64 | Negative over-voltage protection | `over_voltage` |
| 9 | 512 | External inhibit | `inhibit` |
| 11 | 2048 | Coupled protection shutdown | contributes to `active` |
| 12 | 4096 | Oscillation protection | `oscillation` |

Bits 7 and 8 indicate positive/negative limiting. Limiting can be a normal
operating state, so these bits alone do not set the driver's protection
`active` flag.

The Condition register is used because it is a non-destructive live read. The
Questionable Event register is latched and clears when read, so it must not be
used for routine polling.

## Clearing protection

The manual-defined clear command remains:

```text
OUTP:PROT:CLE (@1)
```

The library disables the channel first by default, clears protection, reads the
Questionable Condition register again, and leaves the output OFF unless explicit
restoration was requested.
