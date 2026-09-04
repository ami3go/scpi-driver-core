*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Safe Protection Clear
    Configure N6700 Power Supply Channel    1    5V    1A    output=${TRUE}
    ${result}=    Clear N6700 Protection    1
    Should Be Equal    ${result}[output_state_before]    ${TRUE}
    Should Be Equal    ${result}[output_state_after]     ${FALSE}
    Should Be Equal    ${result}[restored_output]        ${FALSE}

Inspect Error Queue
    Write N6700 SCPI    *CLS
    ${errors}=    Drain N6700 Errors
    Should Be Empty    ${errors}
