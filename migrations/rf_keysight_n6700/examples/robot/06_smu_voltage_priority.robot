*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Configure SMU Voltage Priority
    ${result}=    Configure N6700 SMU Voltage Priority
    ...    2
    ...    1.2V
    ...    200mA
    ...    voltage_limit=2V
    ...    output=${FALSE}
    Should Be Equal    ${result}[mode]    voltage
    ${mode}=    Get N6700 SMU Mode    2
    Should Be Equal    ${mode}    voltage
