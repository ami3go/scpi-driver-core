*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Configure Simulator Load
    ${result}=    Configure N6700 Load CC    3    250mA    input_on=${TRUE}
    Should Be Equal    ${result}[mode]    cc
    ${state}=    Get N6700 Load Input State    3
    Should Be True    ${state}
    ${level}=    Get N6700 Load Level    3    cc
    Should Be Equal As Numbers    ${level}    0.25
