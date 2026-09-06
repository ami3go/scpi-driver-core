*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Query Identity With Raw SCPI
    ${response}=    Query N6700 SCPI    *IDN?
    Should Contain    ${response}    N6700B
