*** Settings ***
Documentation     Offline acceptance suite against the bundled simulator (task §13.2).
...               Covers identity, the RFDS-002 canonical connection lifecycle, channel
...               setup including channel naming, trigger setup, run/stop acquisition,
...               an immediate measurement, a full waveform fetch-and-decode, a
...               screen-image save, a waveform-to-CSV save, and a setup save/restore
...               round trip.
Library           rf_tbs1000c.Tbs1000cLibrary
Library           OperatingSystem
Suite Setup       Connect    alias=default    simulated=${TRUE}
Suite Teardown    Disconnect

*** Variables ***
${SCREEN_IMAGE}    ${OUTPUT DIR}/screen.png
${WAVEFORM_CSV}    ${OUTPUT DIR}/waveform.csv
${SETUP_FILE}      ${OUTPUT DIR}/setup.txt

*** Test Cases ***
Read Identity
    ${identity}=    Get Identity
    Should Contain    ${identity}    TEKTRONIX
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

Configure Channel One Including Its Name
    Set Channel Scale    1    0.5
    Set Channel Position    1    1.0
    Set Channel Coupling    1    AC
    Set Channel Name    1    ICCDATA
    ${settings}=    Get Channel Settings    1
    Should Be Equal As Numbers    ${settings}[scale]    0.5
    Should Be Equal    ${settings}[coupling]    AC
    Should Be Equal    ${settings}[label]    ICCDATA
    [Teardown]    Set Channel Coupling    1    DC

Configure Trigger
    Set Trigger Source    2
    Set Trigger Slope    FALL
    Set Trigger Coupling    DC
    ${settings}=    Get Trigger Settings
    Should Be Equal    ${settings}[source]    CH2
    Should Be Equal    ${settings}[slope]    FALL
    [Teardown]    Set Trigger Source    1

Run Stop Acquisition
    Set Acquisition Mode    SAMPLE
    Start Acquisition
    Stop Acquisition
    ${count}=    Get Acquisition Count
    Should Be True    ${count} >= 0

Immediate Measurement
    Set Channel Scale    1    1.0
    ${frequency}=    Get Immediate Measurement    FREQuency    1
    Should Be True    ${frequency} > 0
    Measurement Should Be Within    FREQuency    1    1.0    1.0E6

Waveform Fetch And Decode
    ${waveform}=    Get Waveform    1
    ${points}=    Get Length    ${waveform}[time_s]
    Should Be True    ${points} > 0
    ${volt_points}=    Get Length    ${waveform}[volts]
    Should Be Equal As Integers    ${points}    ${volt_points}
    Should Not Be Empty    ${waveform}[preamble][x_unit]

Save Screen Image
    Save Screen Image    ${SCREEN_IMAGE}
    File Should Exist    ${SCREEN_IMAGE}

Save Waveform To CSV
    Save Waveform To CSV    ${WAVEFORM_CSV}    1
    File Should Exist    ${WAVEFORM_CSV}

Save And Restore Setup
    Set Channel Scale    1    0.25
    Save Setup    ${SETUP_FILE}
    Set Channel Scale    1    2.0
    Restore Setup    ${SETUP_FILE}
    ${scale}=    Get Channel Scale    1
    Should Be Equal As Numbers    ${scale}    0.25
