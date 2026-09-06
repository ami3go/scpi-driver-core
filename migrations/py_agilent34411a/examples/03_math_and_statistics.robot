*** Settings ***
Documentation     Take a batch of readings under the statistics math function, then
...               configure a limit test. Math functions are mutually exclusive on this
...               instrument (task §6 item 5) — enabling one deselects any other.
Library           rf_agilent34411a.Agilent34411ALibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Statistics Over A Batch Of Readings
    Set Function    VOLT
    Enable Statistics

    FOR    ${index}    IN RANGE    10
        Get Immediate Measurement
    END

    ${stats}=    Get Statistics
    Log    Average=${stats}[average] Min=${stats}[minimum] Max=${stats}[maximum] Count=${stats}[count]
    Should Be Equal As Integers    ${stats}[count]    10

    Clear Statistics
    ${stats}=    Get Statistics
    Should Be Equal As Integers    ${stats}[count]    0
    Disable Math

Limit Test
    Enable Limit Test
    Set Limits    -1.0    1.0
    ${low}    ${high}=    Get Limits
    Should Be Equal As Numbers    ${low}    -1.0
    Should Be Equal As Numbers    ${high}    1.0
    Disable Math

dB And dBm Are Mutually Exclusive With Statistics
    Enable dB Measurement
    Set dB Reference    0.0
    ${active}=    Get Math Function
    Should Be Equal    ${active}    DB

    Enable dBm Measurement
    Set dBm Reference Resistance    600
    ${active}=    Get Math Function
    Should Be Equal    ${active}    DBM

    Disable Math
