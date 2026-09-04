# Code review — v26.06

## Scope

Review of the explicit USB connection API and configured N6775A USB profile.

## Change-by-change review

1. **Public USB keyword:** accepted; it is a thin adapter over the established VISA transport.
2. **Configured resource:** accepted; the exact USBTMC address is preserved and remains overrideable.
3. **Runner defaults:** accepted; USB is now the default, while VISA, Ethernet, socket, and simulator remain selectable.
4. **RFDS updates:** accepted; inventory, vector coverage, AI contract, and lock are regenerated.
5. **Documentation and release metadata:** accepted; v26.06 records and usage examples are present.

## Findings

| Area | Result | Notes |
|---|---|---|
| USB transport mapping | PASS | The new keyword delegates to the existing validated PyVISA transport with `connection_type=usb`. |
| Resource preservation | PASS | `USB0::0x0957::0x0907::MY43014421::INSTR` is passed unchanged to PyVISA. |
| Audit logging | PASS | The explicit USB keyword accepts `audit_log_path`, allowing RFDS-019 command/response evidence. |
| Safety | PASS | Connection remains non-invasive by default; reset and error clearing remain explicit options. |
| Backward compatibility | PASS | Existing generic/VISA/Ethernet methods are unchanged. |
| Testability | PASS | Unit test verifies delegation; RFDS inventory/vector validation covers the new public keyword. |

## Residual risk

Physical opening of the exact USB resource depends on the installed VISA backend, USB cable, Windows driver state, and exclusive resource ownership. This must be confirmed on the real bench.
