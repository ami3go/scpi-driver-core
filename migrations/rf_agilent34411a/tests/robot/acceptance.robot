*** Settings ***
Documentation     Offline acceptance suite against the bundled simulator (task §14.2).
...               Covers identity, the RFDS-002 canonical connection lifecycle, DC and AC
...               voltage measurement configuration and an immediate measurement, 4-wire
...               resistance with offset compensation, statistics, a trigger-source/
...               sample-count round trip, a non-volatile-memory read/clear round trip, and
...               (Gate 3) calibration and LAN configuration round trips.
Library           rf_agilent34411a.Agilent34411ALibrary
Library           Collections
Suite Setup       Connect    alias=default    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Read Identity
    ${identity}=    Get Identity
    Should Contain    ${identity}    Agilent Technologies
    Should Not Be Empty    ${identity}

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

Configure DC Voltage And Measure
    Set Function    VOLT
    Set Range    VOLT    10
    Set Integration Time NPLC    VOLT    10
    ${reading}=    Get Immediate Measurement
    Should Be True    isinstance($reading, float)
    ${settings}=    Get Measurement Settings    VOLT
    Should Be Equal As Numbers    ${settings}[range_value]    10

Configure AC Voltage And Measure
    Set Function    VOLT:AC
    Set AC Filter Bandwidth    VOLT:AC    20
    ${reading}=    Get Immediate Measurement
    Should Be True    isinstance($reading, float)

Four Wire Resistance With Offset Compensation
    Set Function    FRES
    Set Offset Compensation    FRES    ${TRUE}
    ${enabled}=    Get Offset Compensation    FRES
    Should Be True    ${enabled}
    Run Keyword And Expect Error    *ValidationError*    Set Auto Zero    FRES    ON

Statistics
    Set Function    VOLT
    Enable Statistics
    FOR    ${i}    IN RANGE    5
        Get Immediate Measurement
    END
    ${stats}=    Get Statistics
    Should Be True    ${stats}[count] == 5
    Clear Statistics
    Disable Math

Trigger Source And Sample Count Round Trip
    # Reading memory is a genuine FIFO that accumulates across triggers until
    # drained (task §10) — flush whatever earlier test cases left behind first.
    Drain Readings    1000
    Set Trigger Source    BUS
    ${source}=    Get Trigger Source
    Should Be Equal    ${source}    BUS
    Set Sample Count    5
    ${count}=    Get Sample Count
    Should Be Equal As Numbers    ${count}    5
    Trigger Now
    ${reading_count}=    Get Reading Count
    Should Be Equal As Integers    ${reading_count}    5
    Set Trigger Source    IMMediate

Non-Volatile Memory Read And Clear Round Trip
    Set Sample Count    3
    Get Immediate Measurement
    Copy Readings To Non-Volatile Memory
    ${count}=    Get Non-Volatile Reading Count
    Should Be Equal As Integers    ${count}    3
    ${readings}=    Get Non-Volatile Readings
    Length Should Be    ${readings}    3
    Clear Non-Volatile Readings
    ${count}=    Get Non-Volatile Reading Count
    Should Be Equal As Integers    ${count}    0

Calibration Is Blocked Until The Guard Is Enabled
    Run Keyword And Expect Error    *ValidationError*    Run Full Calibration
    Enable Calibration Mode    ENABLE CALIBRATION
    Run Keyword And Expect Error    *DeviceError*    Run Full Calibration
    Unlock Calibration    AT34411A
    ${passed}=    Run Full Calibration
    Should Be True    ${passed}
    Lock Calibration
    ${locked}=    Is Calibration Locked
    Should Be True    ${locked}

Calibration Line Frequency And Value Round Trip
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    AT34411A
    Set Calibration Line Frequency    60
    ${freq}=    Get Calibration Line Frequency
    Should Be Equal As Integers    ${freq}    60
    Set Calibration Value    2.5
    ${value}=    Get Calibration Value
    Should Be Equal As Numbers    ${value}    2.5
    Set Calibration String    Cal Due: 01 August 2027
    ${text}=    Get Calibration String
    Should Be Equal    ${text}    Cal Due: 01 August 2027
    Store Calibration
    Lock Calibration

LAN Configuration Round Trip
    Set LAN Hostname    bench-3-dmm
    ${hostname}=    Get LAN Hostname
    Should Be Equal    ${hostname}    bench-3-dmm
    Set LAN IP Address    10.0.0.5
    ${ip}=    Get LAN IP Address
    Should Be Equal    ${ip}    10.0.0.5
    Set LAN DHCP Enabled    ${FALSE}
    ${dhcp}=    Get LAN DHCP Enabled
    Should Not Be True    ${dhcp}
    ${mac}=    Get LAN MAC Address
    Should Not Be Empty    ${mac}
