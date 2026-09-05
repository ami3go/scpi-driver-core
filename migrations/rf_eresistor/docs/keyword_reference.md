# Keyword reference

## Connection and identity

`Connect To EResistor`, `Disconnect From EResistor`, `E-Resistor Should Be Connected`, `Get EResistor Identity`, `Get EResistor Information`, `Ping EResistor`, and `Identify EResistor`.

## Direct control

`Set EResistor Mask`, `Get EResistor Mask`, `Get All EResistor Masks`, `Set All EResistor Masks`, `Set Selected EResistor Masks`, `Open All EResistor Channels`, and `EResistor Mask Should Be`.

Masks accept integers or hexadecimal strings. Four-digit strings are safest in Robot data. The all-mask keyword takes either one eight-item list or eight values.

## Resistance and calibration

`Download EResistor Calibration`, `Download EResistor Channel Calibration`, `Load EResistor Calibration`, `Save EResistor Calibration`, `Build EResistor Resistance Cache`, `Calculate EResistor Resistance`, `Find Closest EResistor Resistance`, `Set EResistor Resistance`, and `Set Multiple EResistor Resistances`.

Resistance results are dictionaries with `channel`, `requested_ohm`, `calculated_ohm`, `error_ohm`, `error_percent`, `mask`, and `active_bits`.

## Temperature

`Load EResistor Temperature Table`, `Load EResistor Temperature Table For All Channels`, and `Set EResistor Temperature`. CSV columns are `temperature_c,resistance_ohm`; interpolation is `linear` or `log_resistance`.

## Diagnostics and advanced operations

`Send EResistor SCPI Query`, `Get EResistor Status`, `Get EResistor Error`, `Clear EResistor Errors`, `Start EResistor Watchdog`, `Stop EResistor Watchdog`, `Get EResistor Metrics`, `Discover EResistor Boards`, and `Auto Discover EResistor Boards`.

## Evidence

`Export Diagnostic Bundle` — zips the current session's RFDS-008 evidence run
(every keyword call and every SCPI/HTTP exchange, correlated and
SHA-256-manifested) for troubleshooting. See [Logging and evidence](logging_and_evidence.md).

For full generated signatures and embedded docstrings, run Libdoc as described in the README.

