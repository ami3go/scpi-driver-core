*** Settings ***
Documentation     Trigger a batch of readings and persist them to non-volatile memory (the
...               confirmed remote-driven data-logging mechanism, task §10), and save/restore
...               an instrument configuration via the 5 non-volatile MEMory states (task §11).
Library           rf_agilent34411a.Agilent34411ALibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Trigger A Batch And Persist It To Non-Volatile Memory
    Set Function    VOLT
    Set Sample Count    5
    Get Immediate Measurement

    ${count}=    Get Reading Count
    Should Be Equal As Integers    ${count}    5

    Copy Readings To Non-Volatile Memory
    ${nv_count}=    Get Non-Volatile Reading Count
    Should Be Equal As Integers    ${nv_count}    5

    ${readings}=    Get Non-Volatile Readings
    Log    Persisted readings: ${readings}

    Clear Non-Volatile Readings
    ${nv_count}=    Get Non-Volatile Reading Count
    Should Be Equal As Integers    ${nv_count}    0

Save And Restore An Instrument Configuration
    Set Function    VOLT
    Set Range    VOLT    100
    Save Setup To Instrument Memory    1
    Rename Instrument Memory Slot    1    HIGH_RANGE

    Set Range    VOLT    10
    Restore Setup From Instrument Memory    1
    ${range}=    Get Range    VOLT
    Should Be Equal As Numbers    ${range}    100

    ${name}=    Get Instrument Memory Slot Name    1
    Should Be Equal    ${name}    HIGH_RANGE

Restoring An Unsaved Slot Fails Clearly
    Run Keyword And Expect Error    *ValidationError*
    ...    Restore Setup From Instrument Memory    4
