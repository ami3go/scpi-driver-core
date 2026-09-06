*** Settings ***
Documentation     Configure channel/trigger settings, then take an immediate measurement.
Library           rf_tbs1000c.Tbs1000cLibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure Channel One And Measure Frequency
    Set Channel Scale    1    0.5
    Set Channel Coupling    1    DC
    Set Channel Name    1    SIGNAL_A

    Set Trigger Source    1
    Set Trigger Slope    RISE
    Auto Set Trigger Level

    ${frequency}=    Get Immediate Measurement    FREQuency    1
    Log    Measured frequency: ${frequency} Hz
    Measurement Should Be Within    FREQuency    1    1.0    1.0E6
