*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Configure SMU Current Priority
    ${result}=    Configure N6700 SMU Current Priority
    ...    2
    ...    100mA
    ...    3.3V
    ...    output=${FALSE}
    Should Be Equal    ${result}[mode]    current
    Set N6700 SMU Output Off Mode    2    high_z
    ${off_mode}=    Get N6700 SMU Output Off Mode    2
    Should Be Equal    ${off_mode}    high_z
