*** Settings ***
Documentation     Gate 3: demonstrates the two-tier calibration safety guard and a
...               GPIB/LAN interface configuration round trip against the bundled
...               simulator.
Library           rf_agilent33220a.Agilent33220ALibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Calibration Is Blocked Until The Dedicated Guard Is Enabled
    # Calibration has its own confirmation phrase, separate from "Enable Raw
    # SCPI" (task §12) — a caller can't accidentally satisfy one guard while
    # meaning the other.
    Run Keyword And Expect Error    *disabled*    Run Calibration

    Enable Calibration Mode    ENABLE CALIBRATION

    # CAL? itself requires the instrument to be unsecured with its security
    # code (factory default "AT33220A") before it will run.
    Run Keyword And Expect Error    *secured*    Run Calibration
    Unlock Calibration    AT33220A

    ${passed}=    Run Calibration
    Should Be True    ${passed}
    ${count}=    Get Calibration Count
    Should Be True    ${count} >= 1

    Lock Calibration
    ${locked}=    Is Calibration Locked
    Should Be True    ${locked}

Calibration Step Value And String Round Trip
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    AT33220A

    Set Calibration Step    12
    ${step}=    Get Calibration Step
    Should Be Equal As Integers    ${step}    12

    Set Calibration Value    5.0
    ${value}=    Get Calibration Value
    Should Be Equal As Numbers    ${value}    5.0

    Set Calibration String    Cal Due: 01 August 2027
    ${string}=    Get Calibration String
    Should Be Equal    ${string}    Cal Due: 01 August 2027

    Lock Calibration

GPIB And LAN Interface Configuration Round Trip
    Set GPIB Address    12
    ${address}=    Get GPIB Address
    Should Be Equal As Integers    ${address}    12

    Set LAN Auto IP    ${FALSE}
    ${auto_ip}=    Get LAN Auto IP
    Should Not Be True    ${auto_ip}

    Set LAN IP Address    169.254.11.22
    ${ip}=    Get LAN IP Address
    Should Be Equal    ${ip}    169.254.11.22

    ${logical_ip}=    Get LAN Logical IP Address
    Should Not Be Empty    ${logical_ip}
    ${mac}=    Get LAN MAC Address
    Should Not Be Empty    ${mac}

    Set LAN Media Sense Enabled    ${FALSE}
    ${media_sense}=    Get LAN Media Sense Enabled
    Should Not Be True    ${media_sense}

    Set LAN NetBIOS Enabled    ${FALSE}
    ${netbios}=    Get LAN NetBIOS Enabled
    Should Not Be True    ${netbios}

    Set LAN Telnet Prompt    MYGEN>
    ${prompt}=    Get LAN Telnet Prompt
    Should Be Equal    ${prompt}    MYGEN>

    Set LAN Telnet Welcome Message    Welcome to the bench 33220A
    ${welcome}=    Get LAN Telnet Welcome Message
    Should Be Equal    ${welcome}    Welcome to the bench 33220A
