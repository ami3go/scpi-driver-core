*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Verify Voltage Current And Power
    Configure N6700 Power Supply Channel    1    5V    1A    output=${TRUE}
    N6700 Voltage Should Be    1    5V    1mV
    N6700 Current Should Be    1    500mA    1mA
    N6700 Power Should Be      1    2.5W     10mW
