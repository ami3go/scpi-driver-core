*** Settings ***
Documentation     Configure overvoltage/overcurrent/overpower protection thresholds, and
...               demonstrate that a set value outside the currently configured adjustment
...               limit is rejected by the device itself, not pre-validated client-side
...               (task §6 item 5).
Library           rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure Protection Thresholds
    Set Overvoltage Protection    30
    Set Overcurrent Protection    20
    Set Overpower Protection    500

    ${thresholds}=    Get Protection Thresholds
    Log    OVP=${thresholds}[overvoltage] V, OCP=${thresholds}[overcurrent] A, OPP=${thresholds}[overpower] W

Out Of Limit Set Value Is Rejected By The Device
    Set Voltage Limit High    20
    # The device's own -222 "Data out of range" is the source of truth — this
    # driver never pre-empts it with a client-side guess (task §6 item 5).
    Run Keyword And Expect Error    *DeviceError*    Set Voltage    50
    Set Voltage Limit High    81.6

Alarm Counters
    ${counters}=    Get Alarm Counters
    Log    OVP=${counters}[overvoltage] OT=${counters}[overtemperature] OPP=${counters}[overpower] OCP=${counters}[overcurrent] PF=${counters}[power_fail]
