# Code review — v26.07

## Scope

Review of the real-hardware N6775A failure, N6700 protection/OCP SCPI mapping,
status-register parsing, simulator fidelity, and RFDS-019 protocol evidence.

## Root cause

The USB VISA connection was operational. The driver used abbreviated headers
that are not legal short forms in the N6700 command tree:

- invalid: `CURR:PROT?` and `CURR:PROT <Bool>`;
- required: `CURR:PROT:STAT?` and `CURR:PROT:STAT <Bool>`.

It also attempted `OUTP:PROT?`, which is not defined by the N6700 programmer's
reference. Live protection state belongs to the per-channel Questionable
Condition register.

## Change-by-change review

1. **OCP command serialization:** accepted after matching the manual's mandatory `STATe` node.
2. **Protection-status query:** accepted after replacing the undefined output query with the live Questionable Condition register.
3. **Status channel addressing:** accepted after adding explicit channel lists to every status query.
4. **Simulator behavior:** accepted after invalid abbreviations were changed from false-positive support to SCPI rejection.
5. **Regression coverage:** accepted; exact transport commands and decoded register fields are asserted.
6. **Documentation and contracts:** accepted; RFDS vectors, manuals map, history, reviews, and generated contracts are synchronized.

## Findings and actions

| Severity | Finding | Action |
|---|---|---|
| Critical | OCP query timed out and left a pending-query protocol error. | Changed set/query headers to `CURR:PROT:STAT`. |
| High | Generic `OUTP:PROT?` was unsupported and exceptions were silently converted to “no fault.” | Replaced with `STAT:QUES:COND? (@ch)` and removed broad exception suppression. |
| High | Status queries omitted the mandatory channel list. | Added explicit channel lists for single- and multi-channel status reads. |
| Medium | Simulator accepted invalid abbreviations, masking hardware incompatibility. | Simulator now implements manual forms and rejects obsolete commands. |
| Medium | Protocol vectors asserted the invalid commands. | RFDS-019 vectors and trace assertions now require exact manual-defined headers. |

## Safety review

Protection status is now read from the live, non-destructive Condition register.
Event registers are not used for polling because reading them clears latched
events. Current-limit indication bits are not treated as protection trips;
latched OVP/OCP/power/temperature/inhibit/coupled/oscillation bits determine the
`active` result.

## Test evidence

- Exact OCP write/query serialization tests.
- Exact Questionable Condition query test.
- Bit-mask decoding test.
- Simulator rejection tests for obsolete headers.
- Existing driver, Robot simulator, RFDS-019, package, type, lint, documentation,
  wheel, and fixed-root archive gates.

## Residual risk

The corrected release must be rerun on the physical N6700B/N6775A system to
produce final HIL evidence beyond the point where v26.06 timed out.
