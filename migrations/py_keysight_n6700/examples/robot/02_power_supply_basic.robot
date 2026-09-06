*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700
Test Teardown     Shutdown All N6700 Channels

*** Test Cases ***
Configure Twelve Volt Output
    ${config}=    Configure N6700 Power Supply Channel
    ...    1
    ...    12V
    ...    500mA
    ...    output=${FALSE}
    ...    ovp=13V
    ...    ocp=${TRUE}
    Should Be Equal    ${config}[output_enabled]    ${FALSE}
    Turn On N6700 Output    1
    N6700 Output Should Be    1    ${TRUE}
    N6700 Voltage Should Be    1    12V    10mV
