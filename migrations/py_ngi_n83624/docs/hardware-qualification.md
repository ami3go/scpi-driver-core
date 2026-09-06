# Hardware Qualification

Before production use, execute the procedure in `guide/HARDWARE_QUALIFICATION.md` with the exact N83624 model, firmware, DUT fixture, wiring, interlocks, and independent measurement equipment.

Minimum exit criteria:

- Identity and firmware evidence recorded.
- Every used SCPI keyword verified against hardware.
- Output-off behavior verified on normal close, test failure, timeout, cable removal, and process termination.
- Voltage/current limits cross-checked with an independent DMM or DAQ.
- UDP used only after loss/duplication behavior is characterized.
- 8-hour soak and 1000-cycle output tests pass without unexplained state drift.
