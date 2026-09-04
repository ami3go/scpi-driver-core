*** Settings ***
Documentation     Configure DC and AC voltage measurement, then take readings. Demonstrates
...               the 4-wire-resistance always-auto-zero-on safety rule (task §8).
Library           rf_agilent34411a.Agilent34411ALibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure DC Voltage And Measure
    Set Function    VOLT
    Set Range    VOLT    10
    Set Integration Time NPLC    VOLT    10
    Set Auto Zero    VOLT    ON

    ${reading}=    Get Immediate Measurement
    Log    DC voltage reading: ${reading} V

    ${settings}=    Get Measurement Settings    VOLT
    Log    Settings: ${settings}

Configure AC Voltage And Measure
    Set Function    VOLT:AC
    Set AC Filter Bandwidth    VOLT:AC    20
    Set Range    VOLT:AC    1

    ${reading}=    Get Immediate Measurement
    Log    AC voltage reading: ${reading} Vrms

Four Wire Resistance Is Always Auto-Zero On
    Set Function    FRES
    Set Range    FRES    1000
    Set Offset Compensation    FRES    ${TRUE}

    # There is no ZERO:AUTO command for 4-wire resistance on this instrument —
    # attempting to set it raises a typed error instead of silently doing nothing.
    Run Keyword And Expect Error    *ValidationError*    Set Auto Zero    FRES    ON

    ${reading}=    Get Immediate Measurement
    Log    4-wire resistance reading: ${reading} Ohm
