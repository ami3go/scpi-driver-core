# Examples

## Robot Framework examples

The `robot/` folder contains fourteen executable examples:

1. `01_simulator_smoke.robot` — connection, identity, discovery, and measurement.
2. `02_power_supply_basic.robot` — safe PSU channel configuration.
3. `03_measurement_assertions.robot` — voltage/current/power assertions.
4. `04_multi_channel_measurement.robot` — multi-channel workflow.
5. `05_named_sessions.robot` — two named mainframes.
6. `06_smu_voltage_priority.robot` — SMU voltage-priority mode.
7. `07_smu_current_priority.robot` — SMU current-priority mode.
8. `08_electronic_load_cc.robot` — simulator load CC mode.
9. `09_protection_and_errors.robot` — protection and SCPI error handling.
10. `10_real_hardware_readonly.robot` — guarded real-hardware discovery.
11. `11_real_hardware_output_test.robot` — guarded output-changing hardware example.
12. `12_raw_scpi.robot` — raw SCPI query.
13. `13_resource_file_workflow.robot` — reusable resource keywords.
14. `14_wait_for_voltage.robot` — voltage polling.

Run one example:

```bat
scripts\run_example.bat 01_simulator_smoke.robot
```

Run all examples:

```bat
scripts\run_all_examples.bat
```

Examples 10 and 11 skip safely unless hardware variables are supplied.

## Python examples

The `python/` folder contains the original driver examples for VISA, Ethernet, PSU, SMU, electronic load, data logging, status, protection, discovery, binary measurement, and CLI workflows.
