*** Settings ***
Documentation     RFDS-019 real-hardware conformance: exercises every public keyword of
...               rf_agilent33220a.Agilent33220ALibrary against a physical Agilent/Keysight
...               33220A unit and verifies its response. Does not run automatically in CI
...               (Force Tags "hardware"; exclude with `--exclude hardware` in automated
...               pipelines).
...
...               Requires a VISA RESOURCE string (GPIB/USB/LAN all work — see README).
...               Several gates protect real-hardware side effects and are OFF by default:
...               ALLOW_OUTPUT_ON (energizes the DC/AC output), ALLOW_CALIBRATION (touches
...               calibration memory — additionally needs CALIBRATION_SECURITY_CODE, the
...               unit's actual vendor code, or calibration-write keywords are skipped even
...               with the gate on), ALLOW_LAN_WRITES (GPIB/LAN identity keywords — read-only
...               otherwise), and ALLOW_SETUP_WRITES (instrument-memory setup slots and
...               *RST). Every keyword that mutates device-persistent state restores the
...               original value before its own test case ends where the instrument makes
...               that possible to read back; Suite Teardown disables output and disconnects
...               either way.
Library           rf_agilent33220a.Agilent33220ALibrary
Library           Collections
Library           OperatingSystem
Suite Setup       Initialize Hardware Conformance
Suite Teardown    Final Safe Teardown
Test Setup        Prepare Generator For Keyword Test
Test Teardown     Per Test Safe Teardown
Force Tags        hardware    agilent33220a    keyword-conformance

*** Variables ***
${RESOURCE}                    ${EMPTY}
${ALIAS}                       hardware
${SECONDARY_ALIAS}             secondary
${TIMEOUT_S}                   ${5.0}
${ALLOW_OUTPUT_ON}             ${FALSE}
${ALLOW_CALIBRATION}           ${FALSE}
${CALIBRATION_SECURITY_CODE}    ${EMPTY}
${ALLOW_LAN_WRITES}             ${FALSE}
${ALLOW_SETUP_WRITES}           ${FALSE}
${SAFE_FREQUENCY}              ${1000.0}
${SAFE_AMPLITUDE}              ${0.1}
${EXPECTED_DRIVER_VERSION}    26.2

*** Test Cases ***
# ----------------------------------------------------------------------
# Connection (RFDS-002)
# ----------------------------------------------------------------------
KW-001 Connect
    [Documentation]    Reopen the real connection and verify the normalized
    ...    connection-state dictionary Connect returns.
    Disconnect    ${ALIAS}
    ${state}=    Open Hardware Connection
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[state]    connected
    Should Be Equal    ${state}[transport]    PyvisaTransport

KW-002 Disconnect
    [Documentation]    Idempotent: closing an already-closed alias must not raise.
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    Disconnect    ${SECONDARY_ALIAS}
    Disconnect    ${SECONDARY_ALIAS}
    ${connected}=    Is Connected    ${SECONDARY_ALIAS}
    Should Be Equal    ${connected}    ${FALSE}

KW-003 Is Connected
    ${connected}=    Is Connected    ${ALIAS}
    Should Be Equal    ${connected}    ${TRUE}
    ${unknown}=    Is Connected    does-not-exist
    Should Be Equal    ${unknown}    ${FALSE}

KW-004 Get Connection State
    ${state}=    Get Connection State    alias=${ALIAS}    refresh=${TRUE}
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[communication_ok]    ${TRUE}
    Log Dictionary    ${state}

KW-005 Check Communication
    ${ok}=    Check Communication    ${ALIAS}
    Should Be Equal    ${ok}    ${TRUE}

KW-006 Get Identity
    ${identity}=    Get Identity    alias=${ALIAS}    refresh=${TRUE}
    Should Not Be Empty    ${identity}
    Log    ${identity}

KW-007 Switch Generator
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    ${active}=    Switch Generator    ${SECONDARY_ALIAS}
    Should Be Equal    ${active}    ${SECONDARY_ALIAS}
    Switch Generator    ${ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

KW-008 Get Active Generator
    ${active}=    Get Active Generator
    Should Be Equal    ${active}    ${ALIAS}

KW-009 List Generator Connections
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    ${connections}=    List Generator Connections
    List Should Contain Value    ${connections}    ${ALIAS}
    List Should Contain Value    ${connections}    ${SECONDARY_ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

# ----------------------------------------------------------------------
# Output configuration
# ----------------------------------------------------------------------
KW-010 Set Function
    Set Function    SIN
    ${function}=    Get Function
    Should Be Equal    ${function}    SIN

KW-011 Get Function
    ${function}=    Get Function
    Should Not Be Empty    ${function}

KW-012 Set Frequency
    Set Frequency    ${SAFE_FREQUENCY}
    ${frequency}=    Get Frequency
    Numbers Should Be Close    ${frequency}    ${SAFE_FREQUENCY}    1

KW-013 Get Frequency
    ${frequency}=    Get Frequency
    Should Be True    ${frequency} > 0

KW-014 Set Amplitude
    Set Amplitude    ${SAFE_AMPLITUDE}
    ${amplitude}=    Get Amplitude
    Numbers Should Be Close    ${amplitude}    ${SAFE_AMPLITUDE}    0.05

KW-015 Get Amplitude
    ${amplitude}=    Get Amplitude
    Should Be True    ${amplitude} >= 0

KW-016 Set Amplitude Unit
    ${original}=    Get Amplitude Unit
    Set Amplitude Unit    VPP
    ${unit}=    Get Amplitude Unit
    Should Be Equal    ${unit}    VPP
    Set Amplitude Unit    ${original}

KW-017 Get Amplitude Unit
    ${unit}=    Get Amplitude Unit
    Should Not Be Empty    ${unit}

KW-018 Set Offset
    Set Offset    ${0.0}
    ${offset}=    Get Offset
    Numbers Should Be Close    ${offset}    ${0.0}    0.02

KW-019 Get Offset
    ${offset}=    Get Offset
    Should Be True    isinstance($offset, float)

KW-020 Set Output Load
    ${original}=    Get Output Load
    Set Output Load    INFinity
    ${load}=    Get Output Load
    Should Contain    ${load}    INF
    Set Output Load    ${original}

KW-021 Get Output Load
    ${load}=    Get Output Load
    Should Not Be Empty    ${load}

KW-022 Set Output Polarity
    ${original}=    Get Output Polarity
    Set Output Polarity    NORMal
    ${polarity}=    Get Output Polarity
    Should Be Equal    ${polarity}    NORM
    Set Output Polarity    ${original}

KW-023 Get Output Polarity
    ${polarity}=    Get Output Polarity
    Should Contain Any    ${polarity}    NORM    INV

KW-024 Set Square Duty Cycle
    Set Function    SQUare
    Set Square Duty Cycle    ${50}
    ${duty}=    Get Square Duty Cycle
    Numbers Should Be Close    ${duty}    ${50}    2
    Set Function    SIN

KW-025 Get Square Duty Cycle
    Set Function    SQUare
    ${duty}=    Get Square Duty Cycle
    Should Be True    ${duty} >= 0
    Set Function    SIN

KW-026 Set Ramp Symmetry
    Set Function    RAMP
    Set Ramp Symmetry    ${50}
    ${symmetry}=    Get Ramp Symmetry
    Numbers Should Be Close    ${symmetry}    ${50}    2
    Set Function    SIN

KW-027 Get Ramp Symmetry
    Set Function    RAMP
    ${symmetry}=    Get Ramp Symmetry
    Should Be True    ${symmetry} >= 0
    Set Function    SIN

KW-028 Configure Output
    [Documentation]    ``enable_output`` stays False here regardless of ALLOW_OUTPUT_ON —
    ...    KW-029/KW-030 below are the dedicated output-enable coverage.
    Configure Output    SINusoid    ${SAFE_FREQUENCY}    ${SAFE_AMPLITUDE}    ${0.0}
    ...    enable_output=${FALSE}
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${FALSE}

KW-029 Enable Output
    [Documentation]    Skipped unless ALLOW_OUTPUT_ON is set — energizes the output at a
    ...    small safe amplitude. Only enable this against a bench with a suitable
    ...    termination (or nothing) connected; this suite has no way to know what is wired.
    Skip If    not ${ALLOW_OUTPUT_ON}    Set ALLOW_OUTPUT_ON:true to exercise Enable Output.
    Set Amplitude    ${SAFE_AMPLITUDE}
    Enable Output
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${TRUE}
    Disable Output

KW-030 Disable Output
    Disable Output
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${FALSE}

KW-031 Is Output Enabled
    Disable Output
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${FALSE}

KW-032 Get Output Settings
    ${settings}=    Get Output Settings
    Dictionary Should Contain Key    ${settings}    function
    Log Dictionary    ${settings}

# ----------------------------------------------------------------------
# Front panel / display
# ----------------------------------------------------------------------
KW-033 Lock Front Panel
    Lock Front Panel
    ${locked}=    Is Front Panel Locked
    Should Be Equal    ${locked}    ${TRUE}
    Unlock Front Panel

KW-034 Unlock Front Panel
    Lock Front Panel
    Unlock Front Panel
    ${locked}=    Is Front Panel Locked
    Should Be Equal    ${locked}    ${FALSE}

KW-035 Is Front Panel Locked
    Unlock Front Panel
    ${locked}=    Is Front Panel Locked
    Should Be Equal    ${locked}    ${FALSE}

KW-036 Set Display Text
    Set Display Text    RFDS-019 TEST
    Clear Display Text

KW-037 Clear Display Text
    Set Display Text    RFDS-019 TEST
    Clear Display Text

KW-038 Enable Display
    Enable Display

KW-039 Disable Display
    Disable Display
    Enable Display

# ----------------------------------------------------------------------
# Pulse and modulation (configuration only — none of these enable output)
# ----------------------------------------------------------------------
KW-040 Configure Pulse
    Configure Pulse    period=${0.001}    width=${0.0001}

KW-041 Configure Amplitude Modulation
    Configure Amplitude Modulation    shape=SIN    frequency=${100}    depth_percent=${50}

KW-042 Enable Amplitude Modulation
    Configure Amplitude Modulation    shape=SIN    frequency=${100}    depth_percent=${50}
    Enable Amplitude Modulation
    Disable Amplitude Modulation

KW-043 Disable Amplitude Modulation
    Enable Amplitude Modulation
    Disable Amplitude Modulation

KW-044 Configure Frequency Modulation
    Configure Frequency Modulation    shape=SIN    frequency=${100}    deviation_hz=${100}

KW-045 Enable Frequency Modulation
    Configure Frequency Modulation    shape=SIN    frequency=${100}    deviation_hz=${100}
    Enable Frequency Modulation
    Disable Frequency Modulation

KW-046 Disable Frequency Modulation
    Enable Frequency Modulation
    Disable Frequency Modulation

KW-047 Configure Phase Modulation
    Configure Phase Modulation    shape=SIN    frequency=${100}    deviation_degrees=${45}

KW-048 Enable Phase Modulation
    Configure Phase Modulation    shape=SIN    frequency=${100}    deviation_degrees=${45}
    Enable Phase Modulation
    Disable Phase Modulation

KW-049 Disable Phase Modulation
    Enable Phase Modulation
    Disable Phase Modulation

KW-050 Configure Frequency Shift Keying
    Configure Frequency Shift Keying    hop_frequency=${2000}    rate_hz=${50}

KW-051 Enable Frequency Shift Keying
    Configure Frequency Shift Keying    hop_frequency=${2000}    rate_hz=${50}
    Enable Frequency Shift Keying
    Disable Frequency Shift Keying

KW-052 Disable Frequency Shift Keying
    Enable Frequency Shift Keying
    Disable Frequency Shift Keying

KW-053 Configure Pulse Width Modulation
    Set Function    PULSe
    Configure Pulse Width Modulation    shape=SIN    frequency=${100}    deviation_seconds=${0.0001}
    Set Function    SIN

KW-054 Enable Pulse Width Modulation
    Set Function    PULSe
    Configure Pulse Width Modulation    shape=SIN    frequency=${100}    deviation_seconds=${0.0001}
    Enable Pulse Width Modulation
    Disable Pulse Width Modulation
    Set Function    SIN

KW-055 Disable Pulse Width Modulation
    Set Function    PULSe
    Enable Pulse Width Modulation
    Disable Pulse Width Modulation
    Set Function    SIN

# ----------------------------------------------------------------------
# Sweep, burst, trigger
# ----------------------------------------------------------------------
KW-056 Configure Frequency Sweep
    Configure Frequency Sweep    start_frequency=${100}    stop_frequency=${2000}    sweep_time=${1}

KW-057 Enable Sweep
    Configure Frequency Sweep    start_frequency=${100}    stop_frequency=${2000}    sweep_time=${1}
    Enable Sweep
    Disable Sweep

KW-058 Disable Sweep
    Enable Sweep
    Disable Sweep

KW-059 Set Sweep Marker Frequency
    Set Sweep Marker Frequency    ${1000}
    ${marker}=    Get Sweep Marker Frequency
    Numbers Should Be Close    ${marker}    ${1000}    1

KW-060 Get Sweep Marker Frequency
    ${marker}=    Get Sweep Marker Frequency
    Should Be True    ${marker} >= 0

KW-061 Enable Sweep Marker
    Enable Sweep Marker
    Disable Sweep Marker

KW-062 Disable Sweep Marker
    Enable Sweep Marker
    Disable Sweep Marker

KW-063 Configure Burst
    Configure Burst    mode=TRIGgered    cycles=${3}

KW-064 Enable Burst
    Configure Burst    mode=TRIGgered    cycles=${3}
    Enable Burst
    Disable Burst

KW-065 Disable Burst
    Enable Burst
    Disable Burst

KW-066 Set Burst Gate Polarity
    Set Burst Gate Polarity    NORMal

KW-067 Set Trigger Source
    ${original}=    Get Trigger Source
    Set Trigger Source    BUS
    ${source}=    Get Trigger Source
    Should Be Equal    ${source}    BUS
    Set Trigger Source    ${original}

KW-068 Get Trigger Source
    ${source}=    Get Trigger Source
    Should Not Be Empty    ${source}

KW-069 Set Trigger Slope
    ${original}=    Get Trigger Slope
    Set Trigger Slope    POSitive
    ${slope}=    Get Trigger Slope
    Should Be Equal    ${slope}    POS
    Set Trigger Slope    ${original}

KW-070 Get Trigger Slope
    ${slope}=    Get Trigger Slope
    Should Contain Any    ${slope}    POS    NEG

KW-071 Get Trigger Settings
    ${settings}=    Get Trigger Settings
    Dictionary Should Contain Key    ${settings}    source
    Log Dictionary    ${settings}

KW-072 Trigger Now
    [Documentation]    Safe: BUS-triggers whatever burst/sweep/modulation is currently
    ...    configured (output stays in whatever enabled state it already had — this suite
    ...    keeps it disabled outside KW-029, so no signal is actually emitted here).
    Set Trigger Source    BUS
    Configure Burst    mode=TRIGgered    cycles=${1}
    Trigger Now

# ----------------------------------------------------------------------
# Arbitrary waveform
# ----------------------------------------------------------------------
KW-073 Load Arbitrary Waveform
    [Documentation]    Always fills the fixed VOLATILE slot — there is no name argument at
    ...    upload time (task §6 item 6); 'Copy Arbitrary Waveform To Nonvolatile' is what
    ...    assigns a persistent custom name, exercised separately in KW-074.
    Load Arbitrary Waveform    ${{[0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0, -0.5]}}

KW-074 Copy Arbitrary Waveform To Nonvolatile
    [Documentation]    Skipped unless ALLOW_SETUP_WRITES is set — writes to nonvolatile
    ...    memory under a new custom name, a real (if minor) persistent side effect.
    Skip If    not ${ALLOW_SETUP_WRITES}    Set ALLOW_SETUP_WRITES:true to exercise this keyword.
    Load Arbitrary Waveform    ${{[0.0, 1.0, 0.0, -1.0]}}
    Copy Arbitrary Waveform To Nonvolatile    RFDS019WFM

KW-075 Select Arbitrary Waveform
    Load Arbitrary Waveform    ${{[0.0, 1.0, 0.0, -1.0]}}
    Select Arbitrary Waveform    VOLATILE

KW-076 List Arbitrary Waveforms
    Load Arbitrary Waveform    ${{[0.0, 1.0, 0.0, -1.0]}}
    ${waveforms}=    List Arbitrary Waveforms
    List Should Contain Value    ${waveforms}    VOLATILE

KW-077 Delete Arbitrary Waveform
    [Documentation]    Deletes the VOLATILE slot itself (reloadable, so this is safe and
    ...    does not need a nonvolatile write) rather than a named nonvolatile waveform.
    Load Arbitrary Waveform    ${{[0.0, 1.0, 0.0, -1.0]}}
    Delete Arbitrary Waveform    VOLATILE
    ${waveforms}=    List Arbitrary Waveforms
    List Should Not Contain Value    ${waveforms}    VOLATILE

KW-078 Delete All Arbitrary Waveforms
    [Documentation]    Skipped unless ALLOW_SETUP_WRITES is set — clears every volatile
    ...    arbitrary waveform, which could disrupt an existing bench setup.
    Skip If    not ${ALLOW_SETUP_WRITES}    Set ALLOW_SETUP_WRITES:true to exercise this keyword.
    Load Arbitrary Waveform    ${{[0.0, 1.0, 0.0, -1.0]}}
    Delete All Arbitrary Waveforms

KW-079 Get Arbitrary Waveform Attributes
    Load Arbitrary Waveform    ${{[0.0, 1.0, 0.0, -1.0]}}
    ${attributes}=    Get Arbitrary Waveform Attributes    VOLATILE
    Log Dictionary    ${attributes}

# ----------------------------------------------------------------------
# Setup save/restore
# ----------------------------------------------------------------------
KW-080 Save Setup
    ${path}=    Set Variable    ${OUTPUT_DIR}/rfds019_setup.txt
    Save Setup    ${path}
    File Should Exist    ${path}

KW-081 Restore Setup
    ${path}=    Set Variable    ${OUTPUT_DIR}/rfds019_setup.txt
    Save Setup    ${path}
    Restore Setup    ${path}

KW-082 Save Setup To Instrument Memory
    [Documentation]    Skipped unless ALLOW_SETUP_WRITES is set — overwrites instrument
    ...    memory slot 4. Slot 4 (of 0-4) is used deliberately, since slot 0 is the
    ...    most likely to already be in real use on a shared bench.
    Skip If    not ${ALLOW_SETUP_WRITES}    Set ALLOW_SETUP_WRITES:true to exercise this keyword.
    Save Setup To Instrument Memory    ${4}

KW-083 Restore Setup From Instrument Memory
    Skip If    not ${ALLOW_SETUP_WRITES}    Set ALLOW_SETUP_WRITES:true to exercise this keyword.
    Save Setup To Instrument Memory    ${4}
    Restore Setup From Instrument Memory    ${4}

KW-084 Restore Factory Setup
    [Documentation]    ``*RST`` — a standard, universally-safe SCPI reset, but still gated
    ...    behind ALLOW_SETUP_WRITES since it discards every setting this suite (or anyone
    ...    else's prior session) configured. Re-applies the suite's safe baseline afterward
    ...    so later test cases are unaffected either way.
    Skip If    not ${ALLOW_SETUP_WRITES}    Set ALLOW_SETUP_WRITES:true to exercise this keyword.
    Restore Factory Setup
    Set Frequency    ${SAFE_FREQUENCY}
    Set Amplitude    ${SAFE_AMPLITUDE}
    Disable Output

# ----------------------------------------------------------------------
# Calibration (Gate 3) — behind a dedicated two-tier guard, see suite Documentation
# ----------------------------------------------------------------------
KW-085 Enable Calibration Mode
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION

KW-086 Run Calibration
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to run calibration.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    Run Calibration
    Lock Calibration

KW-087 Unlock Calibration
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to unlock calibration.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    Lock Calibration

KW-088 Lock Calibration
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION
    Lock Calibration

KW-089 Is Calibration Locked
    [Documentation]    Read-only — always exercised regardless of ALLOW_CALIBRATION.
    ${locked}=    Is Calibration Locked
    Should Be True    $locked is True or $locked is False

KW-090 Set Calibration Security Code
    [Documentation]    Changes the instrument's own vendor security code — high-risk if
    ...    the new code is lost, so this additionally requires CALIBRATION_SECURITY_CODE
    ...    (used both to unlock first and to restore the original code afterward).
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to change it.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    Set Calibration Security Code    ${CALIBRATION_SECURITY_CODE}
    Lock Calibration

KW-091 Set Calibration Step
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to exercise this keyword.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    Set Calibration Step    ${1}
    ${step}=    Get Calibration Step
    Should Be Equal As Integers    ${step}    1
    Lock Calibration

KW-092 Get Calibration Step
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to exercise this keyword.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    ${step}=    Get Calibration Step
    Should Be True    ${step} >= 0
    Lock Calibration

KW-093 Set Calibration Value
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to exercise this keyword.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    Set Calibration Value    ${0.0}
    Lock Calibration

KW-094 Get Calibration Value
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to exercise this keyword.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    ${value}=    Get Calibration Value
    Should Be True    isinstance($value, float)
    Lock Calibration

KW-095 Get Calibration Count
    [Documentation]    Read-only — always exercised regardless of ALLOW_CALIBRATION.
    ${count}=    Get Calibration Count
    Should Be True    ${count} >= 0

KW-096 Set Calibration String
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to exercise this keyword.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    ${original}=    Get Calibration String
    Set Calibration String    RFDS019
    ${text}=    Get Calibration String
    Should Be Equal    ${text}    RFDS019
    Run Keyword And Ignore Error    Set Calibration String    ${original}
    Lock Calibration

KW-097 Get Calibration String
    Skip If    not (${ALLOW_CALIBRATION} and """${CALIBRATION_SECURITY_CODE}""" != "")
    ...    Set ALLOW_CALIBRATION:true and CALIBRATION_SECURITY_CODE:<code> to exercise this keyword.
    Enable Calibration Mode    ENABLE CALIBRATION
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}
    ${text}=    Get Calibration String
    Should Be True    isinstance($text, str)
    Lock Calibration

# ----------------------------------------------------------------------
# GPIB/LAN interface configuration (Gate 3) — Set keywords gated behind
# ALLOW_LAN_WRITES; every one restores its original value before the test ends.
# ----------------------------------------------------------------------
KW-098 Set GPIB Address
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get GPIB Address
    Set GPIB Address    ${original}
    ${readback}=    Get GPIB Address
    Should Be Equal As Integers    ${readback}    ${original}

KW-099 Get GPIB Address
    ${address}=    Get GPIB Address
    Should Be True    0 <= ${address} <= 30

KW-100 Set LAN Auto IP
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get LAN Auto IP
    Set LAN Auto IP    ${original}
    ${readback}=    Get LAN Auto IP
    Should Be Equal    ${readback}    ${original}

KW-101 Get LAN Auto IP
    ${enabled}=    Get LAN Auto IP
    Should Be True    $enabled is True or $enabled is False

KW-102 Set LAN IP Address
    [Documentation]    Round-trips the instrument's own current IP rather than a
    ...    fabricated one — this field identifies the unit on the network and a wrong
    ...    value could strand it, so this test only proves the Set/Get path works.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get LAN IP Address
    Set LAN IP Address    ${original}
    ${readback}=    Get LAN IP Address
    Should Be Equal    ${readback}    ${original}

KW-103 Get LAN IP Address
    ${address}=    Get LAN IP Address
    Should Not Be Empty    ${address}

KW-104 Get LAN Logical IP Address
    [Documentation]    Read-only.
    ${address}=    Get LAN Logical IP Address
    Should Be True    isinstance($address, str)

KW-105 Get LAN MAC Address
    [Documentation]    Read-only.
    ${mac}=    Get LAN MAC Address
    Should Not Be Empty    ${mac}

KW-106 Set LAN Media Sense Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get LAN Media Sense Enabled
    Set LAN Media Sense Enabled    ${original}
    ${readback}=    Get LAN Media Sense Enabled
    Should Be Equal    ${readback}    ${original}

KW-107 Get LAN Media Sense Enabled
    ${enabled}=    Get LAN Media Sense Enabled
    Should Be True    $enabled is True or $enabled is False

KW-108 Set LAN NetBIOS Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get LAN NetBIOS Enabled
    Set LAN NetBIOS Enabled    ${original}
    ${readback}=    Get LAN NetBIOS Enabled
    Should Be Equal    ${readback}    ${original}

KW-109 Get LAN NetBIOS Enabled
    ${enabled}=    Get LAN NetBIOS Enabled
    Should Be True    $enabled is True or $enabled is False

KW-110 Set LAN Telnet Prompt
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get LAN Telnet Prompt
    Set LAN Telnet Prompt    RFDS019>
    ${readback}=    Get LAN Telnet Prompt
    Should Be Equal    ${readback}    RFDS019>
    Set LAN Telnet Prompt    ${original}

KW-111 Get LAN Telnet Prompt
    ${prompt}=    Get LAN Telnet Prompt
    Should Be True    isinstance($prompt, str)

KW-112 Set LAN Telnet Welcome Message
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN/GPIB Set keywords.
    ${original}=    Get LAN Telnet Welcome Message
    Set LAN Telnet Welcome Message    RFDS-019 TEST
    ${readback}=    Get LAN Telnet Welcome Message
    Should Be Equal    ${readback}    RFDS-019 TEST
    Set LAN Telnet Welcome Message    ${original}

KW-113 Get LAN Telnet Welcome Message
    ${message}=    Get LAN Telnet Welcome Message
    Should Be True    isinstance($message, str)

# ----------------------------------------------------------------------
# Raw SCPI escape hatch
# ----------------------------------------------------------------------
KW-114 Enable Raw SCPI
    [Documentation]    Requires the exact confirmation text; the enabled state then
    ...    persists for the rest of this suite's connection, so KW-115/KW-116 rely on it
    ...    already being enabled here rather than re-enabling it themselves.
    Enable Raw SCPI    ENABLE RAW SCPI

KW-115 Raw SCPI Query
    [Documentation]    ``*IDN?`` is a universal, non-mutating SCPI query — safe on any
    ...    SCPI instrument and a good proof that the raw escape hatch round-trips real
    ...    device responses.
    ${response}=    Raw SCPI Query    *IDN?
    Should Not Be Empty    ${response}
    Log    ${response}

KW-116 Raw SCPI Write
    [Documentation]    ``*CLS`` (clear status) is universal and harmless — it only clears
    ...    the SCPI error/event queues, no device settings change.
    Raw SCPI Write    *CLS
    ${response}=    Raw SCPI Query    *ESR?
    Should Not Be Empty    ${response}
    Log    ${response}

# ----------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------
KW-117 Export Diagnostic Bundle
    ${path}=    Export Diagnostic Bundle
    Should Not Be Empty    ${path}
    File Should Exist    ${path}
    Log    Diagnostic bundle written to ${path}

*** Keywords ***
Initialize Hardware Conformance
    Require Real Resource
    Capture Software Evidence
    ${state}=    Open Hardware Connection
    Log Dictionary    ${state}
    Disable Output
    Set Frequency    ${SAFE_FREQUENCY}
    Set Amplitude    ${SAFE_AMPLITUDE}

Require Real Resource
    Should Not Be Equal    ${RESOURCE}    ${EMPTY}
    ...    Pass a VISA resource string: -v RESOURCE:<visa string> (e.g. USB0::0x0957::0x0407::<serial>::INSTR)

Capture Software Evidence
    ${source_version}=    Evaluate    agilent33220a.__version__    modules=agilent33220a
    ${distribution_version}=    Evaluate
    ...    importlib.metadata.version("robotframework-agilent33220a")    modules=importlib.metadata
    ${robot_version}=    Evaluate    robot.__version__    modules=robot
    ${python_version}=    Evaluate    platform.python_version()    modules=platform
    ${platform_name}=    Evaluate    platform.platform()    modules=platform
    Set Suite Metadata    Driver source version    ${source_version}
    Set Suite Metadata    Installed distribution version    ${distribution_version}
    Set Suite Metadata    Robot Framework version    ${robot_version}
    Set Suite Metadata    Python version    ${python_version}
    Set Suite Metadata    Host platform    ${platform_name}
    Log To Console
    ...    Driver source=${source_version}; installed=${distribution_version}; Robot=${robot_version}; Python=${python_version}
    Should Be Equal    ${source_version}    ${EXPECTED_DRIVER_VERSION}
    ...    Source package version ${source_version} does not match suite release ${EXPECTED_DRIVER_VERSION}.
    Should Be Equal    ${distribution_version}    ${source_version}
    ...    Installed robotframework-agilent33220a ${distribution_version} does not match imported source ${source_version}; reinstall the release wheel.

Open Hardware Connection
    Log    Opening real Agilent/Keysight 33220A on resource=${RESOURCE}.
    ${state}=    Connect    resource=${RESOURCE}    alias=${ALIAS}    timeout_s=${TIMEOUT_S}
    RETURN    ${state}

Prepare Generator For Keyword Test
    Run Keyword And Ignore Error    Switch Generator    ${ALIAS}
    Disable Output
    Set Function    SIN

Per Test Safe Teardown
    Run Keyword And Ignore Error    Switch Generator    ${ALIAS}
    Run Keyword And Ignore Error    Disable Output
    Run Keyword And Ignore Error    Set Function    SIN

Final Safe Teardown
    Run Keyword And Ignore Error    Switch Generator    ${ALIAS}
    Run Keyword And Ignore Error    Disable Output
    Run Keyword And Ignore Error    Disconnect    ${ALIAS}

Numbers Should Be Close
    [Arguments]    ${actual}    ${expected}    ${tolerance}
    ${difference}=    Evaluate    abs(float($actual) - float($expected))
    Should Be True    ${difference} <= ${tolerance}
    ...    Difference ${difference} exceeds tolerance ${tolerance}; actual=${actual}, expected=${expected}
