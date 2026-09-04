*** Settings ***
Library    rf_hp34401a.Hp34401ALibrary
Suite Teardown    Disconnect All

*** Test Cases ***
Canonical Universal API Is Callable
    ${state}=    Connect    resource=SIM::HP34401A    alias=dut
    Should Be True    ${state}[connected]
    Should Be True    Is Connected    alias=dut
    ${connection}=    Get Connection State    alias=dut
    Should Be True    Check Communication    alias=dut
    ${identity}=    Get Identity    alias=dut
    ${information}=    Get Driver Information
    ${capabilities}=    Get Driver Capabilities
    ${timeout}=    Set Communication Timeout    5.0    alias=dut
    ${timeout}=    Get Communication Timeout    alias=dut
    Disconnect    alias=dut
