# SCPI Command Map

| Python API method | SCPI command/query | Official source | Supported module models | Capability flag | Simulator test | Hardware test | Safety notes |
|---|---|---|---|---|---|---|---|
| `N6700.idn` | `*IDN?` | N6700 Programmer's Reference, Common Commands | All mainframes | n/a | `test_idn_parse` | `test_hw_idn` | Read-only |
| `N6700.channel_count` | `SYSTem:CHANnel:COUNt?` | N6700 Programmer's Reference, SYSTem subsystem | All mainframes | n/a | `test_discovery` | `test_hw_discovery` | Read-only |
| `N6700.channel_model` | `SYSTem:CHANnel:MODel?` | N6700 Programmer's Reference, SYSTem subsystem | All mainframes | n/a | `test_discovery` | `test_hw_discovery` | Read-only |
| `N6700.channel_options` | `SYSTem:CHANnel:OPTion?` | N6700 Programmer's Reference, SYSTem subsystem | All mainframes | n/a | `test_discovery` | `test_hw_discovery` | Read-only |
| `PowerSupplyChannel.output_on/off` | `OUTPut <Bool>,(@ch)` | N6700 Programmer's Reference, OUTPut subsystem | Power/SMU modules | `supports_voltage_source` | `test_power_output` | level 2 only | Energizes DUT when ON |
| `PowerSupplyChannel.set_voltage_setpoint` | `VOLTage[:LEVel] <value>,(@ch)` | N6700 Programmer's Reference, SOURce subsystem | Power/SMU modules | `supports_voltage_source` | `test_voltage_current_config` | level 1 output off | Does not enable output |
| `PowerSupplyChannel.set_current_limit` | `CURRent[:LEVel] <value>,(@ch)` | N6700 Programmer's Reference, SOURce subsystem | Power/SMU modules | n/a | `test_voltage_current_config` | level 1 output off | Does not enable output |
| `PowerSupplyChannel.set_ocp/get_ocp` | `CURRent:PROTection:STATe <Bool>,(@ch)` / `CURRent:PROTection:STATe? (@ch)` | N6700 Programmer's Reference, SOURce subsystem | Power/SMU modules | n/a | `test_ocp_uses_manual_defined_state_header_and_round_trips` | level 1 output off | OCP state; `STATe` is mandatory and cannot be omitted |
| `BaseChannel.get_protection_status` | `STATus:QUEStionable:CONDition? (@ch)` | N6700 Programmer's Reference, STATus subsystem | All output modules | n/a | `test_protection_status_uses_questionable_condition_and_decodes_bits` | read-only | Non-destructive live status query; do not substitute `OUTP:PROT?` |
| `SMUChannel.set_smu_mode` | `FUNCtion:MODE VOLT/CURR,(@ch)` | N6700 Programmer's Reference, SOURce/SMU function mode | N678xA | `supports_smu_priority_mode` | `test_smu_mode` | optional | Does not enable output |
| `ElectronicLoadChannel.*` | `SIM:LOAD:*` | Simulator-only, not real hardware SCPI | `SIM_LOAD` only | `supports_load_*` | `test_sim_load` | none | Real load commands blocked until exact official source is added |
| `BaseChannel.clear_protection` | `OUTPut:PROTection:CLEar (@ch)` | N6700 Programmer's Reference, OUTPut subsystem | Output modules | n/a | `test_safe_clear_protection` | guarded | Driver forces output off first by default |

> **N6775A power measurement:** the module does not support direct `MEAS:POW?`. The library reads `MEAS:VOLT?` and `MEAS:CURR?`, calculates watts, and reports `power_source=calculated`.
