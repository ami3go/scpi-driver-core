*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Resource   ../../resources/N6700Common.resource
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700
Test Teardown     Safe Test Teardown

*** Test Cases ***
Use Reusable Safe Keywords
    Configure Safe DC Output    1    12V    500mA    13V
    Enable Output And Verify Voltage    1    11.9V    12.1V
