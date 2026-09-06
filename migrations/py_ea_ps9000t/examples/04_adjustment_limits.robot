*** Settings ***
Documentation     Configure the adjustment limits ("Limits" in the front-panel setup
...               menu). Note the asymmetric power-limit shape — there is no "power limit
...               low" on this instrument family (task §9).
Library           rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure Adjustment Limits
    Set Voltage Limit Low    1
    Set Voltage Limit High    50
    Set Current Limit Low    0.5
    Set Current Limit High    30
    Set Power Limit High    800

    ${limits}=    Get Adjustment Limits
    Log    Voltage: ${limits}[voltage_low]-${limits}[voltage_high] V
    Log    Current: ${limits}[current_low]-${limits}[current_high] A
    Log    Power: up to ${limits}[power_high] W (no power low limit exists)

    Should Be Equal As Numbers    ${limits}[voltage_low]    1
    Should Be Equal As Numbers    ${limits}[voltage_high]    50
    Should Be Equal As Numbers    ${limits}[power_high]    800
