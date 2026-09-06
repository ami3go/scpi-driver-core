*** Settings ***
Documentation     Offline acceptance suite against the bundled simulator (task §12.2).
...               Covers identity, the RFDS-002 canonical connection lifecycle including
...               remote-control acquisition/release, set voltage/current/power and an
...               immediate measurement, overvoltage/overcurrent/overpower protection
...               threshold configuration, output enable/disable, adjustment limits, a
...               device-configuration round trip, and (Gate 3) LAN and analog-interface
...               configuration round trips.
Library           rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup       Connect    alias=default    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Read Identity
    ${identity}=    Get Identity
    Should Contain    ${identity}    EA-Elektro-Automatik
    Should Not Be Empty    ${identity}

Connect Acquires Remote Control
    ${owner}=    Get Remote Control Owner
    Should Be Equal    ${owner}    REMOTE

Connect Is Idempotent For The Same Resource
    ${first}=    Connect    alias=default    simulated=${TRUE}
    ${second}=    Connect    alias=default    simulated=${TRUE}
    Should Be Equal    ${first}[identity]    ${second}[identity]

Is Connected And Get Connection State
    ${connected}=    Is Connected
    Should Be True    ${connected}
    ${state}=    Get Connection State
    Should Be Equal    ${state}[state]    connected

Check Communication
    ${ok}=    Check Communication
    Should Be True    ${ok}

Set Voltage Current Power And Measure
    Set Voltage    24
    Set Current    5
    Set Power    200
    ${voltage}=    Get Voltage
    Should Be Equal As Numbers    ${voltage}    24
    ${values}=    Get Measured Values
    Should Be True    isinstance($values, dict)

Protection Thresholds
    Set Overvoltage Protection    30
    Set Overcurrent Protection    20
    Set Overpower Protection    500
    ${thresholds}=    Get Protection Thresholds
    Should Be Equal As Numbers    ${thresholds}[overvoltage]    30
    Should Be Equal As Numbers    ${thresholds}[overcurrent]    20
    Should Be Equal As Numbers    ${thresholds}[overpower]    500

Output Enable Disable
    ${enabled}=    Is Output Enabled
    Should Not Be True    ${enabled}
    Enable Output
    ${enabled}=    Is Output Enabled
    Should Be True    ${enabled}
    Disable Output

Adjustment Limits
    Set Voltage Limit High    50
    Set Current Limit High    30
    Set Power Limit High    800
    ${limits}=    Get Adjustment Limits
    Should Be Equal As Numbers    ${limits}[voltage_high]    50
    Should Be Equal As Numbers    ${limits}[current_high]    30
    Should Be Equal As Numbers    ${limits}[power_high]    800

Device Configuration Round Trip
    Set Power Stage After Remote    OFF
    ${mode}=    Get Power Stage After Remote
    Should Be Equal    ${mode}    OFF
    Set User Text    bench 3
    ${text}=    Get User Text
    Should Be Equal    ${text}    bench 3

LAN Configuration Round Trip
    Set LAN DHCP Enabled    ${TRUE}
    ${dhcp}=    Get LAN DHCP Enabled
    Should Be True    ${dhcp}
    Set LAN IP Address    192.168.1.50
    ${ip}=    Get LAN IP Address
    Should Be Equal    ${ip}    192.168.1.50
    Run Keyword And Expect Error    *ValidationError*    Set LAN Control Port    502
    ${mac}=    Get LAN MAC Address
    Should Not Be Empty    ${mac}

Analog Interface Configuration Round Trip
    Set Analog Reference Range    5
    ${range}=    Get Analog Reference Range
    Should Be Equal As Numbers    ${range}    5
    Set Analog REMSB Level    INVERTED
    ${level}=    Get Analog REMSB Level
    Should Be Equal    ${level}    INVERTED
    Set Analog REMSB Action    AUTO
    ${action}=    Get Analog REMSB Action
    Should Be Equal    ${action}    AUTO
