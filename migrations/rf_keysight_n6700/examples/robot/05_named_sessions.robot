*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Use Two Named Instruments
    Connect To Simulated N6700    left
    Connect To Simulated N6700    right
    ${aliases}=    Get Connected N6700 Aliases
    Should Contain    ${aliases}    left
    Should Contain    ${aliases}    right
    Select N6700    left
    Set N6700 Voltage    1    5V
    Set N6700 Voltage    1    12V    alias=right
    ${left}=    Get N6700 Voltage Setpoint    1
    Should Be Equal As Numbers    ${left}    5
    ${right}=    Get N6700 Voltage Setpoint    1    right
    Should Be Equal As Numbers    ${right}    12
