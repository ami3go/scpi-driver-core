*** Settings ***
Documentation     Offline acceptance suite against the bundled simulator (task §14.2).
...               Covers identity, the RFDS-002 canonical connection lifecycle, output
...               configuration via both the low-level keywords and Configure
...               Output/Enable Output, amplitude modulation, frequency sweep with the
...               marker keywords, burst, front-panel lock/unlock, an arbitrary waveform
...               upload and selection, a setup save/restore round trip, the two-tier
...               calibration guard with a step/value/string round trip (Gate 3), and
...               GPIB/LAN interface configuration (Gate 3).
Library           rf_agilent33220a.Agilent33220ALibrary
Library           OperatingSystem
Library           Collections
Suite Setup       Connect    alias=default    simulated=${TRUE}
Suite Teardown    Disconnect

*** Variables ***
${SETUP_FILE}    ${OUTPUT DIR}/setup.txt

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

Configure Output Via Low Level Keywords
    Set Function    SINusoid
    Set Frequency    1000
    Set Amplitude    1.0
    Set Offset    0.0
    ${settings}=    Get Output Settings
    Should Be Equal    ${settings}[function]    SIN
    Should Be Equal As Numbers    ${settings}[frequency]    1000
    Should Be Equal As Numbers    ${settings}[amplitude]    1.0
    Should Not Be True    ${settings}[output_enabled]

Configure Output And Enable Output
    Configure Output    SQUare    2000    2.0    0.0
    ${enabled}=    Is Output Enabled
    Should Not Be True    ${enabled}    Configure Output must not enable the output implicitly
    Enable Output
    ${enabled}=    Is Output Enabled
    Should Be True    ${enabled}
    Disable Output

Amplitude Modulation
    Configure Amplitude Modulation    SINusoid    100    50
    Enable Amplitude Modulation
    Disable Amplitude Modulation

Frequency Sweep With Marker
    Configure Frequency Sweep    100    10000    LINear    1.0
    Enable Sweep
    Set Sweep Marker Frequency    5000
    ${marker_frequency}=    Get Sweep Marker Frequency
    Should Be Equal As Numbers    ${marker_frequency}    5000
    Enable Sweep Marker
    Disable Sweep Marker
    Disable Sweep

Burst
    Configure Burst    TRIGgered    5    period=0.01
    Enable Burst
    Disable Burst

Front Panel Lock Round Trip
    Lock Front Panel
    ${locked}=    Is Front Panel Locked
    Should Be True    ${locked}
    Unlock Front Panel
    ${locked}=    Is Front Panel Locked
    Should Not Be True    ${locked}

Arbitrary Waveform Upload And Selection
    Load Arbitrary Waveform    ${{[0.0, 1.0, -1.0, 0.5]}}
    Copy Arbitrary Waveform To Nonvolatile    MYWAVE
    ${names}=    List Arbitrary Waveforms
    List Should Contain Value    ${names}    MYWAVE
    Select Arbitrary Waveform    MYWAVE
    ${function}=    Get Function
    Should Be Equal    ${function}    USER

Save And Restore Setup
    Set Frequency    12345
    Save Setup    ${SETUP_FILE}
    Set Frequency    100
    Restore Setup    ${SETUP_FILE}
    ${frequency}=    Get Frequency
    Should Be Equal As Numbers    ${frequency}    12345

Calibration Is Blocked Until The Guard Is Enabled
    Run Keyword And Expect Error    *disabled*    Run Calibration
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    AT33220A
    ${passed}=    Run Calibration
    Should Be True    ${passed}
    Lock Calibration

Calibration Step Value And String Round Trip
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    AT33220A
    Set Calibration Step    7
    ${step}=    Get Calibration Step
    Should Be Equal As Integers    ${step}    7
    Set Calibration Value    2.5
    ${value}=    Get Calibration Value
    Should Be Equal As Numbers    ${value}    2.5
    Set Calibration String    Cal Due: 2027
    ${string}=    Get Calibration String
    Should Be Equal    ${string}    Cal Due: 2027
    Lock Calibration

GPIB And LAN Interface Configuration Round Trip
    Set GPIB Address    12
    ${address}=    Get GPIB Address
    Should Be Equal As Integers    ${address}    12
    Set LAN IP Address    192.168.1.50
    ${ip}=    Get LAN IP Address
    Should Be Equal    ${ip}    192.168.1.50
    Set LAN Media Sense Enabled    ${FALSE}
    ${media_sense}=    Get LAN Media Sense Enabled
    Should Not Be True    ${media_sense}
    ${mac}=    Get LAN MAC Address
    Should Not Be Empty    ${mac}
