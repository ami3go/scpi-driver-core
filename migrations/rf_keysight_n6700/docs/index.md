# RF Keysight N6700

Robot Framework library and typed Python driver for Keysight/Agilent N6700-series modular power systems.

**Release:** v26.09  
**Python package:** `robotframework-keysight-n6700==26.9.0`

The implementation has two layers:

1. `keysight_n6700` provides transports, module capabilities, typed channel APIs, SCPI handling, safety policy, and the simulator.
2. `KeysightN6700Library` exposes Robot Framework keywords, named sessions, engineering-unit conversion, assertions, polling, and Robot-friendly return values.

## Minimal example

```robotframework
*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Basic Output
    Configure N6700 Power Supply Channel    1    5V    500mA    output=${TRUE}
    N6700 Voltage Should Be    1    5V    50mV
```

## Start here

- [Installation](guide/installation.md)
- [PyCharm and Robot Framework setup](guide/pycharm_robot_framework_setup.md)
- [Robot Framework guide](robot_framework/guide.md)
- [Keyword summary](robot_framework/keyword_summary.md)
- [Examples](examples.md)
- [Safety](safety.md)
- [Project package standard](project_package_standard.md)
- [AI driver and bench contracts](ai_contracts.md)
- [Release history](release/history_v26.09.md)
- [Code review](release/code_review_v26.09.md)

The generated complete keyword reference is included as `KeysightN6700Library.html` in the release repository.

## AI planning interface

Use `ai/keysight_n6700_ai_contract.yaml` for single-driver planning and `system_ai_contract.yaml` for bench-level planning. The bench template blocks energization until all physical UNKNOWN values are resolved and approved.
