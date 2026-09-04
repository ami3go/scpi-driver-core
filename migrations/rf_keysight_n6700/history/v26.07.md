# Release history — v26.07

- **Version:** 26.07
- **Python package:** 26.7.0
- **Archive:** `rf_keysight_n6700_v26.07.zip`
- **Date:** 2026-07-24

## Defect evidence

The real N6700B/N6775A USB run connected successfully through
`USB0::0x0957::0x0907::MY43014421::INSTR`, read the mainframe identity, and
discovered both N6775A modules. Execution then timed out at the OCP query and
the instrument reported undefined-header and unterminated-query errors.

## Corrections

1. Replaced the invalid OCP commands `CURR:PROT <Bool>` and
   `CURR:PROT?` with the programmer-manual forms
   `CURR:PROT:STAT <Bool>,(@ch)` and `CURR:PROT:STAT? (@ch)`.
2. Replaced the nonexistent generic protection query `OUTP:PROT?` with the
   non-destructive per-channel status query `STAT:QUES:COND? (@ch)`.
3. Added decoding of the N6700 Questionable Condition register into OVP, OCP,
   power-fail, power-limit, over-temperature, inhibit, coupled-protection, and
   oscillation status.
4. Corrected driver operation/questionable status methods to include the
   mandatory channel list and preserve multi-channel responses.
5. Updated the simulator to model the manual-defined command forms and reject
   the obsolete abbreviations with SCPI error `-113`.
6. Added exact outbound-command regression tests and protection-bit decoding
   tests.
7. Updated the RFDS-019 N6775A self-check, protocol vectors, SCPI command map,
   protection documentation, AI contracts, Libdoc, distributions, and release
   metadata.

## Compatibility

The USB VISA resource and connection mechanism are unchanged. Existing public
Robot Framework keyword names and signatures are unchanged; only their SCPI
serialization and protection-status implementation were corrected.
