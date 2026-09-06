# Production Safety Guide

This package is designed to be conservative, but it cannot make a test bench safe by software alone.

## Mandatory limits

The N83624 programming guide does not fully define model-specific electrical limits. Before enabling outputs in production, configure `InstrumentLimits` and `ChannelLimits` using values verified against your exact instrument model, firmware, labels, calibration sheet, cabling, fixtures, DUT, and test plan.

By default, `DriverSafetyPolicy.require_limits_before_output_on=True`; output enable is rejected unless voltage and current maximums are configured for the channel.

## External interlock

Implement `BenchInterlock` to connect the driver with bench state:

- emergency stop OK;
- contactor closed/open as intended;
- DUT connected and safe;
- thermal chamber state valid;
- operator authorization for fault simulation.

## Fault simulation

Fault simulation relay switching is disabled by default. To use it:

1. set `DriverSafetyPolicy.fault_simulation_enabled=True`;
2. provide a bench interlock or deliberately use `NullBenchInterlock` only in a safe lab setup;
3. use source mode only;
4. allow the driver to turn output off;
5. wait until measured voltage and current fall below thresholds;
6. verify event/status bits after switching.

Capacitive DUTs, BMS inputs, EMI filters, and long cables may store energy after simulator output is switched off. Increase `settle_timeout_s`, lower `voltage_zero_threshold_v`, or use external discharge/measurement hardware as appropriate.

## Communication loss

If communication is lost while an output may be ON, the software cannot prove the real output state. Treat this as a bench fault. Recommended response:

- mark test invalid;
- stop external loads/sources where possible;
- trigger bench-level safe state;
- reconnect;
- query all channel states;
- require operator/test-framework acknowledgement before resuming.

## Factory reset and persistent settings

`factory_reset()`, `set_ip_address()`, `set_lan_connection_type()`, `set_serial_baudrate()`, and `set_powerdown_save()` require confirmation by default. These commands can change persistent configuration and break communication.
