# Writing and Running Robot Framework Tests

## Recommended suite skeleton

```robotframework
*** Settings ***
Library           rf_keysight_n6700.KeysightN6700Library    auto_shutdown=${TRUE}    strict_errors=${TRUE}
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700
Test Teardown     Shutdown All N6700 Channels

*** Test Cases ***
Safe Output Test
    Configure N6700 Power Supply Channel    1    5V    100mA    output=${FALSE}
    Turn On N6700 Output    1
    N6700 Voltage Should Be    1    5V    50mV
    Turn Off N6700 Output    1
```

## Use engineering units

Prefer explicit units in test data:

```robotframework
Set N6700 Voltage    1    12V
Set N6700 Current    1    500mA
Wait For N6700 Voltage    1    11.9V    12.1V    timeout=5s
```

## Use aliases for multiple instruments

```robotframework
Connect To Simulated N6700    supply_a
Connect To Simulated N6700    supply_b
Select N6700    supply_a
```

## Reusable resource file

`resources/N6700Common.resource` contains safe reusable workflow keywords. Example 13 demonstrates importing it from `examples/robot/`.

## Run examples

```bat
scripts\run_example.bat 03_measurement_assertions.robot
scripts\run_all_examples.bat
```

Results are written below `build/` and are not mixed with source files.
