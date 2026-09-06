*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Measure Multiple Channels
    Configure N6700 Power Supply Channel    1    3.3V    1A
    Configure N6700 Power Supply Channel    2    1.8V    500mA
    Set N6700 Outputs    1,2    ${TRUE}
    ${measurements}=    Measure All N6700 Channels
    Should Be Equal As Numbers    ${measurements}[1][voltage_V]    3.3
    Should Be Equal As Numbers    ${measurements}[2][voltage_V]    1.8
