# Release history — v26.06

- **Version:** 26.06
- **Python package:** 26.6.0
- **Archive:** `rf_keysight_n6700_v26.06.zip`
- **Date:** 2026-07-24

## Changes

1. Added the explicit Robot Framework keyword `Connect To N6700 Via USB`.
2. Added the configured N6775A USBTMC VISA resource `USB0::0x0957::0x0907::MY43014421::INSTR`.
3. Updated the N6775A PowerShell, BAT, and shell runners to default to USB and this resource while preserving environment/argument overrides.
4. Updated the RFDS-019 self-check setup to exercise the explicit USB keyword and retain protocol audit logging.
5. Added unit and conformance coverage for USB keyword delegation and USB protocol-vector mapping.
6. Updated RFDS-017/RFDS-019 inventories, contracts, documentation, Libdoc, build artifacts, and release metadata.

## Compatibility

Existing VISA, raw Ethernet, socket, and simulator connection workflows remain supported. `Connect To N6700 Via VISA` remains unchanged.
