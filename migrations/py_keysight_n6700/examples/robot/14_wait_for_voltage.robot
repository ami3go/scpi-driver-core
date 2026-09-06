*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Wait For Programmed Voltage
    Configure N6700 Power Supply Channel    1    3.3V    1A    output=${TRUE}
    ${actual}=    Wait Until N6700 Voltage Is In Range
    ...    1
    ...    3.29V
    ...    3.31V
    ...    timeout=2s
    ...    poll_interval=50ms
    Should Be Equal As Numbers    ${actual}    3.3
