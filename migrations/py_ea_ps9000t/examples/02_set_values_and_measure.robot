*** Settings ***
Documentation     Configure voltage/current/power, enable the output, and read back the
...               measured values.
Library           rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure Output And Measure
    Set Voltage    24
    Set Current    5
    Set Power    200

    ${voltage}=    Get Voltage
    ${current}=    Get Current
    ${power}=    Get Power
    Log    Set values: ${voltage} V, ${current} A, ${power} W

    Enable Output
    ${enabled}=    Is Output Enabled
    Should Be True    ${enabled}

    ${values}=    Get Measured Values
    Log    Measured: ${values}[voltage] V, ${values}[current] A, ${values}[power] W

    Disable Output

Discover Connected Unit Ratings
    # The correct way to discover a connected unit's actual ratings — never
    # hardcode a model's numbers (task §1).
    ${ratings}=    Get Nominal Ratings
    Log    Nominal: ${ratings}[voltage] V, ${ratings}[current] A, ${ratings}[power] W
    ${device_class}=    Get Device Class
    Log    Device class: ${device_class}
