*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Discover Simulator
    ${identity}=    Get N6700 Identity
    Should Be Equal    ${identity}[model]    N6700B
    ${count}=    Get N6700 Channel Count
    Should Be Equal As Integers    ${count}    4
    ${modules}=    Discover N6700 Modules
    Log    ${modules}
    ${all}=    Measure All N6700 Channels
    Log    ${all}
