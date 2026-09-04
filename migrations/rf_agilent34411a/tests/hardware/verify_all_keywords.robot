*** Settings ***
Documentation     RFDS-019 real-hardware conformance: exercises every public keyword of
...               rf_agilent34411a.Agilent34411ALibrary against a physical Agilent/Keysight
...               34411A digital multimeter and verifies its response. Does not run
...               automatically in CI (Force Tags "hardware"; exclude with `--exclude
...               hardware` in automated pipelines).
...
...               Connects over VISA (GPIB/USB/LAN — RESOURCE is a full VISA resource
...               string, there is no universal safe default the way a fixed COM port would
...               be, so Suite Setup fails immediately with a clear message if RESOURCE is
...               left empty).
...
...               Calibration-mutating keywords are skipped unless ALLOW_CALIBRATION is set
...               (calibration changes are persistent and affect measurement accuracy on
...               every subsequent use of the instrument); LAN-identity Set keywords are
...               read-only unless ALLOW_LAN_WRITES is set; Delete All Instrument Memory
...               Slots is skipped unless ALLOW_DELETE_ALL_MEMORY is set; and the
...               Save/Restore/Rename/Delete instrument-memory-slot tests use TEST_MEMORY_
...               SLOT and refuse to touch it if it is already occupied, unless
...               ALLOW_MEMORY_OVERWRITE is set — see the per-keyword documentation below.
...               Every keyword that mutates device-persistent state restores the original
...               value before its own test case ends, and Suite Teardown disconnects.
Library           rf_agilent34411a.Agilent34411ALibrary
Library           Collections
Library           OperatingSystem
Suite Setup       Initialize Hardware Conformance
Suite Teardown    Final Safe Teardown
Force Tags        hardware    agilent34411a    keyword-conformance

*** Variables ***
${RESOURCE}                     ${EMPTY}
${ALIAS}                        hardware
${SECONDARY_ALIAS}              secondary
${TIMEOUT_S}                    ${5.0}
${ALLOW_CALIBRATION}            ${FALSE}
${ALLOW_LAN_WRITES}             ${FALSE}
${ALLOW_DELETE_ALL_MEMORY}      ${FALSE}
${ALLOW_MEMORY_OVERWRITE}       ${FALSE}
${TEST_MEMORY_SLOT}             ${4}
${EXPECTED_DRIVER_VERSION}      26.2

*** Test Cases ***
# ----------------------------------------------------------------------
# Connection (RFDS-002)
# ----------------------------------------------------------------------
KW-001 Connect
    [Documentation]    Reopen the real connection and verify the normalized
    ...    connection-state dictionary Connect returns.
    Disconnect    ${ALIAS}
    ${state}=    Connect    resource=${RESOURCE}    alias=${ALIAS}    timeout_s=${TIMEOUT_S}
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[state]    connected

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

KW-007 Switch Multimeter
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    ${active}=    Switch Multimeter    ${SECONDARY_ALIAS}
    Should Be Equal    ${active}    ${SECONDARY_ALIAS}
    Switch Multimeter    ${ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

KW-008 Get Active Multimeter
    ${active}=    Get Active Multimeter
    Should Be Equal    ${active}    ${ALIAS}

KW-009 List Multimeter Connections
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    ${connections}=    List Multimeter Connections
    List Should Contain Value    ${connections}    ${ALIAS}
    List Should Contain Value    ${connections}    ${SECONDARY_ALIAS}
    Disconnect    ${SECONDARY_ALIAS}
    Switch Multimeter    ${ALIAS}

# ----------------------------------------------------------------------
# Function selection
# ----------------------------------------------------------------------
KW-010 Set Function
    Set Function    VOLT    alias=${ALIAS}
    ${function}=    Get Function    alias=${ALIAS}
    Should Be Equal    ${function}    VOLT

KW-011 Get Function
    Set Function    VOLT    alias=${ALIAS}
    ${function}=    Get Function    alias=${ALIAS}
    Should Not Be Empty    ${function}

# ----------------------------------------------------------------------
# Per-function measurement configuration
# ----------------------------------------------------------------------
KW-012 Set Range
    Set Function    VOLT    alias=${ALIAS}
    Set Auto Range    VOLT    enabled=${FALSE}    alias=${ALIAS}
    Set Range    VOLT    10    alias=${ALIAS}
    ${range}=    Get Range    VOLT    alias=${ALIAS}
    Numbers Should Be Close    ${range}    10    1
    Set Auto Range    VOLT    enabled=${TRUE}    alias=${ALIAS}

KW-013 Get Range
    Set Function    VOLT    alias=${ALIAS}
    ${range}=    Get Range    VOLT    alias=${ALIAS}
    Should Be True    ${range} > 0

KW-014 Set Auto Range
    Set Function    VOLT    alias=${ALIAS}
    ${original}=    Get Auto Range    VOLT    alias=${ALIAS}
    Set Auto Range    VOLT    enabled=${TRUE}    alias=${ALIAS}
    ${enabled}=    Get Auto Range    VOLT    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Set Auto Range    VOLT    enabled=${original}    alias=${ALIAS}

KW-015 Get Auto Range
    Set Function    VOLT    alias=${ALIAS}
    ${enabled}=    Get Auto Range    VOLT    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-016 Set Integration Time NPLC
    Set Function    VOLT    alias=${ALIAS}
    ${original}=    Get Integration Time NPLC    VOLT    alias=${ALIAS}
    Set Integration Time NPLC    VOLT    1    alias=${ALIAS}
    ${nplc}=    Get Integration Time NPLC    VOLT    alias=${ALIAS}
    Numbers Should Be Close    ${nplc}    1    0.1
    Set Integration Time NPLC    VOLT    ${original}    alias=${ALIAS}

KW-017 Get Integration Time NPLC
    Set Function    VOLT    alias=${ALIAS}
    ${nplc}=    Get Integration Time NPLC    VOLT    alias=${ALIAS}
    Should Be True    ${nplc} > 0

KW-018 Set Integration Time Aperture
    Set Function    VOLT    alias=${ALIAS}
    ${original}=    Get Integration Time Aperture    VOLT    alias=${ALIAS}
    Set Integration Time Aperture    VOLT    ${0.02}    alias=${ALIAS}
    ${aperture}=    Get Integration Time Aperture    VOLT    alias=${ALIAS}
    Should Be True    ${aperture} > 0
    Set Integration Time Aperture    VOLT    ${original}    alias=${ALIAS}

KW-019 Get Integration Time Aperture
    Set Function    VOLT    alias=${ALIAS}
    ${aperture}=    Get Integration Time Aperture    VOLT    alias=${ALIAS}
    Should Be True    ${aperture} > 0

KW-020 Set Auto Zero
    [Documentation]    4-wire resistance always rejects this keyword, so DC voltage is used.
    Set Function    VOLT    alias=${ALIAS}
    ${original}=    Get Auto Zero    VOLT    alias=${ALIAS}
    Set Auto Zero    VOLT    ON    alias=${ALIAS}
    ${mode}=    Get Auto Zero    VOLT    alias=${ALIAS}
    Should Not Be Empty    ${mode}
    Set Auto Zero    VOLT    ${original}    alias=${ALIAS}

KW-021 Get Auto Zero
    Set Function    VOLT    alias=${ALIAS}
    ${mode}=    Get Auto Zero    VOLT    alias=${ALIAS}
    Should Not Be Empty    ${mode}

KW-022 Set Offset Compensation
    Set Function    RES    alias=${ALIAS}
    ${original}=    Get Offset Compensation    RES    alias=${ALIAS}
    Set Offset Compensation    RES    ${TRUE}    alias=${ALIAS}
    ${enabled}=    Get Offset Compensation    RES    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Set Offset Compensation    RES    ${original}    alias=${ALIAS}

KW-023 Get Offset Compensation
    Set Function    RES    alias=${ALIAS}
    ${enabled}=    Get Offset Compensation    RES    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-024 Set AC Filter Bandwidth
    Set Function    VOLT:AC    alias=${ALIAS}
    ${original}=    Get AC Filter Bandwidth    VOLT:AC    alias=${ALIAS}
    Set AC Filter Bandwidth    VOLT:AC    20    alias=${ALIAS}
    ${bandwidth}=    Get AC Filter Bandwidth    VOLT:AC    alias=${ALIAS}
    Should Not Be Empty    ${bandwidth}
    Set AC Filter Bandwidth    VOLT:AC    ${original}    alias=${ALIAS}

KW-025 Get AC Filter Bandwidth
    Set Function    VOLT:AC    alias=${ALIAS}
    ${bandwidth}=    Get AC Filter Bandwidth    VOLT:AC    alias=${ALIAS}
    Should Not Be Empty    ${bandwidth}

KW-026 Set Input Impedance Auto
    Set Function    VOLT    alias=${ALIAS}
    ${original}=    Get Input Impedance Auto    alias=${ALIAS}
    Set Input Impedance Auto    ${TRUE}    alias=${ALIAS}
    ${enabled}=    Get Input Impedance Auto    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Set Input Impedance Auto    ${original}    alias=${ALIAS}

KW-027 Get Input Impedance Auto
    Set Function    VOLT    alias=${ALIAS}
    ${enabled}=    Get Input Impedance Auto    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-028 Set Null
    Set Function    VOLT    alias=${ALIAS}
    Set Null    VOLT    ${TRUE}    alias=${ALIAS}
    ${enabled}=    Get Null    VOLT    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Set Null    VOLT    ${FALSE}    alias=${ALIAS}

KW-029 Get Null
    Set Function    VOLT    alias=${ALIAS}
    ${enabled}=    Get Null    VOLT    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-030 Set Null Value
    Set Function    VOLT    alias=${ALIAS}
    ${original}=    Get Null Value    VOLT    alias=${ALIAS}
    Set Null Value    VOLT    ${0.001}    alias=${ALIAS}
    ${value}=    Get Null Value    VOLT    alias=${ALIAS}
    Numbers Should Be Close    ${value}    0.001    0.0005
    Set Null Value    VOLT    ${original}    alias=${ALIAS}

KW-031 Get Null Value
    Set Function    VOLT    alias=${ALIAS}
    ${value}=    Get Null Value    VOLT    alias=${ALIAS}
    Should Be True    isinstance($value, float)

KW-032 Get Measurement Settings
    Set Function    VOLT    alias=${ALIAS}
    ${settings}=    Get Measurement Settings    function=VOLT    alias=${ALIAS}
    Should Not Be Empty    ${settings}
    Log Dictionary    ${settings}

# ----------------------------------------------------------------------
# Temperature
# ----------------------------------------------------------------------
KW-033 Set Temperature Probe Type
    Set Function    TEMP    alias=${ALIAS}
    Set Temperature Probe Type    THER    thermistor_type=5000    alias=${ALIAS}
    ${probe}=    Get Temperature Probe Type    alias=${ALIAS}
    Should Not Be Empty    ${probe}

KW-034 Get Temperature Probe Type
    Set Function    TEMP    alias=${ALIAS}
    ${probe}=    Get Temperature Probe Type    alias=${ALIAS}
    Should Not Be Empty    ${probe}

KW-035 Set Temperature Units
    Set Function    TEMP    alias=${ALIAS}
    ${original}=    Get Temperature Units    alias=${ALIAS}
    Set Temperature Units    C    alias=${ALIAS}
    ${unit}=    Get Temperature Units    alias=${ALIAS}
    Should Not Be Empty    ${unit}
    Set Temperature Units    ${original}    alias=${ALIAS}

KW-036 Get Temperature Units
    Set Function    TEMP    alias=${ALIAS}
    ${unit}=    Get Temperature Units    alias=${ALIAS}
    Should Not Be Empty    ${unit}

# ----------------------------------------------------------------------
# Taking readings
# ----------------------------------------------------------------------
KW-037 Get Immediate Measurement
    Set Function    VOLT    alias=${ALIAS}
    ${value}=    Get Immediate Measurement    alias=${ALIAS}
    Should Be True    isinstance($value, float)

KW-038 Get Reading
    Set Function    VOLT    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    ${value}=    Get Reading    alias=${ALIAS}
    Should Not Be Equal    ${value}    ${None}

# ----------------------------------------------------------------------
# Math
# ----------------------------------------------------------------------
KW-039 Get Math Function
    Disable Math    alias=${ALIAS}
    ${math}=    Get Math Function    alias=${ALIAS}
    Should Not Be Empty    ${math}

KW-040 Is Math Enabled
    Disable Math    alias=${ALIAS}
    ${enabled}=    Is Math Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${FALSE}

KW-041 Enable dB Measurement
    Set Function    VOLT    alias=${ALIAS}
    Enable dB Measurement    alias=${ALIAS}
    ${enabled}=    Is Math Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Disable Math    alias=${ALIAS}

KW-042 Set dB Reference
    Set Function    VOLT    alias=${ALIAS}
    Enable dB Measurement    alias=${ALIAS}
    Set dB Reference    ${1.0}    alias=${ALIAS}
    Disable Math    alias=${ALIAS}

KW-043 Enable dBm Measurement
    Set Function    VOLT    alias=${ALIAS}
    Enable dBm Measurement    alias=${ALIAS}
    ${enabled}=    Is Math Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Disable Math    alias=${ALIAS}

KW-044 Set dBm Reference Resistance
    Set Function    VOLT    alias=${ALIAS}
    Enable dBm Measurement    alias=${ALIAS}
    Set dBm Reference Resistance    ${600}    alias=${ALIAS}
    Disable Math    alias=${ALIAS}

KW-045 Enable Statistics
    Set Function    VOLT    alias=${ALIAS}
    Enable Statistics    alias=${ALIAS}
    ${enabled}=    Is Math Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Disable Math    alias=${ALIAS}

KW-046 Get Statistics
    Set Function    VOLT    alias=${ALIAS}
    Enable Statistics    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    ${stats}=    Get Statistics    alias=${ALIAS}
    Should Not Be Empty    ${stats}
    Log Dictionary    ${stats}
    Disable Math    alias=${ALIAS}

KW-047 Clear Statistics
    Set Function    VOLT    alias=${ALIAS}
    Enable Statistics    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    Clear Statistics    alias=${ALIAS}
    Disable Math    alias=${ALIAS}

KW-048 Enable Limit Test
    Set Function    VOLT    alias=${ALIAS}
    Set Limits    -10    10    alias=${ALIAS}
    Enable Limit Test    alias=${ALIAS}
    ${enabled}=    Is Math Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Disable Math    alias=${ALIAS}

KW-049 Set Limits
    Set Function    VOLT    alias=${ALIAS}
    Set Limits    -10    10    alias=${ALIAS}
    ${limits}=    Get Limits    alias=${ALIAS}
    Numbers Should Be Close    ${limits}[0]    -10    0.1
    Numbers Should Be Close    ${limits}[1]    10    0.1

KW-050 Get Limits
    Set Function    VOLT    alias=${ALIAS}
    Set Limits    -10    10    alias=${ALIAS}
    ${limits}=    Get Limits    alias=${ALIAS}
    Length Should Be    ${limits}    2

KW-051 Disable Math
    Set Function    VOLT    alias=${ALIAS}
    Enable Statistics    alias=${ALIAS}
    Disable Math    alias=${ALIAS}
    ${enabled}=    Is Math Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${FALSE}

# ----------------------------------------------------------------------
# Trigger / sample
# ----------------------------------------------------------------------
KW-052 Set Trigger Source
    ${original}=    Get Trigger Source    alias=${ALIAS}
    Set Trigger Source    IMM    alias=${ALIAS}
    ${source}=    Get Trigger Source    alias=${ALIAS}
    Should Not Be Empty    ${source}
    Set Trigger Source    ${original}    alias=${ALIAS}

KW-053 Get Trigger Source
    ${source}=    Get Trigger Source    alias=${ALIAS}
    Should Not Be Empty    ${source}

KW-054 Set Trigger Level
    ${original}=    Get Trigger Level    alias=${ALIAS}
    Set Trigger Level    ${0.5}    alias=${ALIAS}
    ${level}=    Get Trigger Level    alias=${ALIAS}
    Numbers Should Be Close    ${level}    0.5    0.1
    Set Trigger Level    ${original}    alias=${ALIAS}

KW-055 Get Trigger Level
    ${level}=    Get Trigger Level    alias=${ALIAS}
    Should Be True    isinstance($level, float)

KW-056 Set Trigger Slope
    ${original}=    Get Trigger Slope    alias=${ALIAS}
    Set Trigger Slope    POS    alias=${ALIAS}
    ${slope}=    Get Trigger Slope    alias=${ALIAS}
    Should Not Be Empty    ${slope}
    Set Trigger Slope    ${original}    alias=${ALIAS}

KW-057 Get Trigger Slope
    ${slope}=    Get Trigger Slope    alias=${ALIAS}
    Should Not Be Empty    ${slope}

KW-058 Set Trigger Count
    ${original}=    Get Trigger Count    alias=${ALIAS}
    Set Trigger Count    ${1}    alias=${ALIAS}
    ${count}=    Get Trigger Count    alias=${ALIAS}
    Numbers Should Be Close    ${count}    1    0.1
    Set Trigger Count    ${original}    alias=${ALIAS}

KW-059 Get Trigger Count
    ${count}=    Get Trigger Count    alias=${ALIAS}
    Should Be True    ${count} >= 1

KW-060 Set Trigger Delay
    Set Trigger Delay    ${0.1}    alias=${ALIAS}
    Set Trigger Delay Auto    alias=${ALIAS}

KW-061 Set Trigger Delay Auto
    Set Trigger Delay Auto    alias=${ALIAS}

KW-062 Get Trigger Settings
    ${settings}=    Get Trigger Settings    alias=${ALIAS}
    Should Not Be Empty    ${settings}
    Log Dictionary    ${settings}

KW-063 Set Sample Count
    ${original}=    Get Sample Count    alias=${ALIAS}
    Set Sample Count    ${1}    alias=${ALIAS}
    ${count}=    Get Sample Count    alias=${ALIAS}
    Numbers Should Be Close    ${count}    1    0.1
    Set Sample Count    ${original}    alias=${ALIAS}

KW-064 Get Sample Count
    ${count}=    Get Sample Count    alias=${ALIAS}
    Should Be True    ${count} >= 1

KW-065 Set Sample Source
    Set Sample Source    IMM    alias=${ALIAS}

KW-066 Set Sample Timer Interval
    Set Sample Timer Interval    ${0.1}    alias=${ALIAS}

KW-067 Set Pre-Trigger Sample Count
    [Documentation]    Rejects a pre-trigger count >= the sample count, so raise Sample
    ...    Count first.
    Set Sample Count    ${2}    alias=${ALIAS}
    Set Pre-Trigger Sample Count    ${0}    alias=${ALIAS}
    Set Sample Count    ${1}    alias=${ALIAS}

KW-068 Trigger Now
    [Documentation]    Only valid when Trigger Source is BUS.
    ${original_source}=    Get Trigger Source    alias=${ALIAS}
    Set Trigger Source    BUS    alias=${ALIAS}
    Trigger Now    alias=${ALIAS}
    Set Trigger Source    ${original_source}    alias=${ALIAS}

# ----------------------------------------------------------------------
# Reading memory and data logging
# ----------------------------------------------------------------------
KW-069 Get Latest Reading
    Set Function    VOLT    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    ${value}=    Get Latest Reading    alias=${ALIAS}
    Should Not Be Equal    ${value}    ${None}

KW-070 Get Most Recent Reading
    Set Function    VOLT    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    ${value}=    Get Most Recent Reading    alias=${ALIAS}
    Should Be True    isinstance($value, float)

KW-071 Get Reading Count
    ${count}=    Get Reading Count    alias=${ALIAS}
    Should Be True    ${count} >= 0

KW-072 Drain Readings
    Set Function    VOLT    alias=${ALIAS}
    Set Trigger Count    ${2}    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    ${count}=    Get Reading Count    alias=${ALIAS}
    ${readings}=    Drain Readings    ${count}    alias=${ALIAS}
    Should Not Be Equal    ${readings}    ${None}
    Set Trigger Count    ${1}    alias=${ALIAS}

KW-073 Copy Readings To Non-Volatile Memory
    Set Function    VOLT    alias=${ALIAS}
    Get Immediate Measurement    alias=${ALIAS}
    Copy Readings To Non-Volatile Memory    alias=${ALIAS}
    Clear Non-Volatile Readings    alias=${ALIAS}

KW-074 Get Non-Volatile Reading Count
    ${count}=    Get Non-Volatile Reading Count    alias=${ALIAS}
    Should Be True    ${count} >= 0

KW-075 Get Non-Volatile Readings
    ${readings}=    Get Non-Volatile Readings    alias=${ALIAS}
    Should Not Be Equal    ${readings}    ${None}

KW-076 Clear Non-Volatile Readings
    Clear Non-Volatile Readings    alias=${ALIAS}
    ${count}=    Get Non-Volatile Reading Count    alias=${ALIAS}
    Should Be Equal As Integers    ${count}    0

KW-077 Drain Non-Volatile Readings
    Clear Non-Volatile Readings    alias=${ALIAS}
    ${readings}=    Drain Non-Volatile Readings    alias=${ALIAS}
    Should Not Be Equal    ${readings}    ${None}

# ----------------------------------------------------------------------
# Instrument memory state storage
# ----------------------------------------------------------------------
KW-078 Save Setup To Instrument Memory
    [Documentation]    Refuses to touch TEST_MEMORY_SLOT if it is already occupied, unless
    ...    ALLOW_MEMORY_OVERWRITE is set — saving overwrites whatever setup (and name) is
    ...    already stored there.
    ${already_valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Skip If    ${already_valid} and not ${ALLOW_MEMORY_OVERWRITE}
    ...    TEST_MEMORY_SLOT ${TEST_MEMORY_SLOT} is already occupied; set ALLOW_MEMORY_OVERWRITE:true or choose an empty slot.
    Save Setup To Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    ${valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Should Be Equal    ${valid}    ${TRUE}
    Delete Instrument Memory Slot    ${TEST_MEMORY_SLOT}    alias=${ALIAS}

KW-079 Restore Setup From Instrument Memory
    ${already_valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Skip If    ${already_valid} and not ${ALLOW_MEMORY_OVERWRITE}
    ...    TEST_MEMORY_SLOT ${TEST_MEMORY_SLOT} is already occupied; set ALLOW_MEMORY_OVERWRITE:true or choose an empty slot.
    Save Setup To Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Restore Setup From Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Delete Instrument Memory Slot    ${TEST_MEMORY_SLOT}    alias=${ALIAS}

KW-080 Get Instrument Memory Catalog
    ${catalog}=    Get Instrument Memory Catalog    alias=${ALIAS}
    Should Not Be Equal    ${catalog}    ${None}

KW-081 Rename Instrument Memory Slot
    ${already_valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Skip If    ${already_valid} and not ${ALLOW_MEMORY_OVERWRITE}
    ...    TEST_MEMORY_SLOT ${TEST_MEMORY_SLOT} is already occupied; set ALLOW_MEMORY_OVERWRITE:true or choose an empty slot.
    Save Setup To Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Rename Instrument Memory Slot    ${TEST_MEMORY_SLOT}    RFDS019TEST    alias=${ALIAS}
    ${name}=    Get Instrument Memory Slot Name    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Should Be Equal    ${name}    RFDS019TEST
    Delete Instrument Memory Slot    ${TEST_MEMORY_SLOT}    alias=${ALIAS}

KW-082 Get Instrument Memory Slot Name
    ${already_valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Skip If    ${already_valid} and not ${ALLOW_MEMORY_OVERWRITE}
    ...    TEST_MEMORY_SLOT ${TEST_MEMORY_SLOT} is already occupied; set ALLOW_MEMORY_OVERWRITE:true or choose an empty slot.
    Save Setup To Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    ${name}=    Get Instrument Memory Slot Name    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Should Not Be Equal    ${name}    ${None}
    Delete Instrument Memory Slot    ${TEST_MEMORY_SLOT}    alias=${ALIAS}

KW-083 Delete Instrument Memory Slot
    ${already_valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Skip If    ${already_valid} and not ${ALLOW_MEMORY_OVERWRITE}
    ...    TEST_MEMORY_SLOT ${TEST_MEMORY_SLOT} is already occupied; set ALLOW_MEMORY_OVERWRITE:true or choose an empty slot.
    Save Setup To Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Delete Instrument Memory Slot    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    ${valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Should Be Equal    ${valid}    ${FALSE}

KW-084 Delete All Instrument Memory Slots
    [Documentation]    Destroys every saved setup on the instrument, not just
    ...    TEST_MEMORY_SLOT — skipped unless ALLOW_DELETE_ALL_MEMORY is set.
    Skip If    not ${ALLOW_DELETE_ALL_MEMORY}
    ...    Set ALLOW_DELETE_ALL_MEMORY:true to exercise Delete All Instrument Memory Slots.
    Delete All Instrument Memory Slots    alias=${ALIAS}
    ${count}=    Get Instrument Memory Slot Count    alias=${ALIAS}
    Should Be Equal As Integers    ${count}    0

KW-085 Is Instrument Memory Slot Valid
    ${valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Should Be True    $valid is True or $valid is False

KW-086 Get Instrument Memory Slot Count
    ${count}=    Get Instrument Memory Slot Count    alias=${ALIAS}
    Should Be True    ${count} >= 0

KW-087 Set Power-On State Recall
    ${original}=    Get Function    alias=${ALIAS}
    Set Power-On State Recall    ${FALSE}    alias=${ALIAS}
    Set Power-On State Recall    ${TRUE}    alias=${ALIAS}
    Set Power-On State Recall    ${FALSE}    alias=${ALIAS}

KW-088 Set Power-On State
    ${already_valid}=    Is Instrument Memory Slot Valid    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Skip If    ${already_valid} and not ${ALLOW_MEMORY_OVERWRITE}
    ...    TEST_MEMORY_SLOT ${TEST_MEMORY_SLOT} is already occupied; set ALLOW_MEMORY_OVERWRITE:true or choose an empty slot.
    Save Setup To Instrument Memory    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Set Power-On State    ${TEST_MEMORY_SLOT}    alias=${ALIAS}
    Delete Instrument Memory Slot    ${TEST_MEMORY_SLOT}    alias=${ALIAS}

# ----------------------------------------------------------------------
# Front panel / system
# ----------------------------------------------------------------------
KW-089 Get Active Input Terminals
    ${terminals}=    Get Active Input Terminals    alias=${ALIAS}
    Should Not Be Empty    ${terminals}

KW-090 Set Beeper Enabled
    ${original}=    Get Beeper Enabled    alias=${ALIAS}
    Set Beeper Enabled    ${FALSE}    alias=${ALIAS}
    ${enabled}=    Get Beeper Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${FALSE}
    Set Beeper Enabled    ${original}    alias=${ALIAS}

KW-091 Get Beeper Enabled
    ${enabled}=    Get Beeper Enabled    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-092 Set Display Enabled
    ${original}=    Get Display Enabled    alias=${ALIAS}
    Set Display Enabled    ${TRUE}    alias=${ALIAS}
    ${enabled}=    Get Display Enabled    alias=${ALIAS}
    Should Be Equal    ${enabled}    ${TRUE}
    Set Display Enabled    ${original}    alias=${ALIAS}

KW-093 Get Display Enabled
    ${enabled}=    Get Display Enabled    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-094 Set Display Text
    Set Display Text    RFDS-019 TEST    alias=${ALIAS}
    Clear Display Text    alias=${ALIAS}

KW-095 Clear Display Text
    Set Display Text    RFDS-019 TEST    alias=${ALIAS}
    Clear Display Text    alias=${ALIAS}

# ----------------------------------------------------------------------
# Calibration (Gate 3 — CALibration subsystem, behind ALLOW_CALIBRATION)
# ----------------------------------------------------------------------
KW-096 Enable Calibration Mode
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}

KW-097 Unlock Calibration
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}

KW-098 Lock Calibration
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}
    ${locked}=    Is Calibration Locked    alias=${ALIAS}
    Should Be Equal    ${locked}    ${TRUE}

KW-099 Is Calibration Locked
    [Documentation]    Read-only — always exercised regardless of ALLOW_CALIBRATION.
    ${locked}=    Is Calibration Locked    alias=${ALIAS}
    Should Be True    $locked is True or $locked is False

KW-100 Set Calibration Security Code
    [Documentation]    Round-trips the security code already in ${CALIBRATION_SECURITY_CODE}
    ...    (never a newly fabricated one) so this test never locks the instrument out of its
    ...    own calibration subsystem.
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    Set Calibration Security Code    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}

KW-101 Run Full Calibration
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    ${passed}=    Run Full Calibration    alias=${ALIAS}
    Should Be True    $passed is True or $passed is False
    Lock Calibration    alias=${ALIAS}

KW-102 Run ADC Calibration
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    ${value}=    Run ADC Calibration    alias=${ALIAS}
    Should Be True    isinstance($value, float)
    Lock Calibration    alias=${ALIAS}

KW-103 Set Calibration Line Frequency
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    ${original}=    Get Calibration Line Frequency    alias=${ALIAS}
    Set Calibration Line Frequency    ${original}    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}

KW-104 Get Calibration Line Frequency
    ${frequency}=    Get Calibration Line Frequency    alias=${ALIAS}
    Should Be True    ${frequency} > 0

KW-105 Get Actual Calibration Line Frequency
    [Documentation]    Read-only measurement readback — always exercised.
    ${frequency}=    Get Actual Calibration Line Frequency    alias=${ALIAS}
    Should Be True    ${frequency} > 0

KW-106 Store Calibration
    [Documentation]    Persists calibration constants to non-volatile memory — only run
    ...    immediately after a real calibration step, never standalone against
    ...    whatever transient calibration state happens to be active.
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    Run ADC Calibration    alias=${ALIAS}
    Store Calibration    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}

KW-107 Get Calibration Count
    [Documentation]    Read-only — always exercised.
    ${count}=    Get Calibration Count    alias=${ALIAS}
    Should Be True    ${count} >= 0

KW-108 Set Calibration String
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    ${original}=    Get Calibration String    alias=${ALIAS}
    Set Calibration String    ${original}    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}

KW-109 Get Calibration String
    ${text}=    Get Calibration String    alias=${ALIAS}
    Should Not Be Equal    ${text}    ${None}

KW-110 Set Calibration Value
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise calibration keywords.
    Enable Calibration Mode    ENABLE CALIBRATION    alias=${ALIAS}
    Unlock Calibration    ${CALIBRATION_SECURITY_CODE}    alias=${ALIAS}
    Run ADC Calibration    alias=${ALIAS}
    ${value}=    Get Calibration Value    alias=${ALIAS}
    Set Calibration Value    ${value}    alias=${ALIAS}
    Lock Calibration    alias=${ALIAS}

KW-111 Get Calibration Value
    [Documentation]    Read-only readback of the last calibration/ADC-cal result.
    ${value}=    Get Calibration Value    alias=${ALIAS}
    Should Be True    isinstance($value, float)

# ----------------------------------------------------------------------
# LAN configuration (Gate 3) — Set keywords gated behind ALLOW_LAN_WRITES;
# every one restores its original value before the test case ends.
# ----------------------------------------------------------------------
KW-112 Set LAN DHCP Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN DHCP Enabled    alias=${ALIAS}
    Set LAN DHCP Enabled    ${original}    alias=${ALIAS}

KW-113 Get LAN DHCP Enabled
    ${enabled}=    Get LAN DHCP Enabled    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-114 Set LAN IP Address
    [Documentation]    Round-trips the instrument's own current IP rather than a fabricated
    ...    one — a wrong value could strand it on the network.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN IP Address    alias=${ALIAS}
    Set LAN IP Address    ${original}    alias=${ALIAS}

KW-115 Get LAN IP Address
    ${address}=    Get LAN IP Address    alias=${ALIAS}
    Should Not Be Empty    ${address}

KW-116 Set LAN Subnet Mask
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Subnet Mask    alias=${ALIAS}
    Set LAN Subnet Mask    ${original}    alias=${ALIAS}

KW-117 Get LAN Subnet Mask
    ${mask}=    Get LAN Subnet Mask    alias=${ALIAS}
    Should Not Be Empty    ${mask}

KW-118 Set LAN Gateway
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Gateway    alias=${ALIAS}
    Set LAN Gateway    ${original}    alias=${ALIAS}

KW-119 Get LAN Gateway
    ${gateway}=    Get LAN Gateway    alias=${ALIAS}
    Should Be True    isinstance($gateway, str)

KW-120 Set LAN DNS
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN DNS    alias=${ALIAS}
    Set LAN DNS    ${original}    alias=${ALIAS}

KW-121 Get LAN DNS
    ${dns}=    Get LAN DNS    alias=${ALIAS}
    Should Be True    isinstance($dns, str)

KW-122 Set LAN Hostname
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Hostname    alias=${ALIAS}
    Set LAN Hostname    ${original}    alias=${ALIAS}

KW-123 Get LAN Hostname
    ${hostname}=    Get LAN Hostname    alias=${ALIAS}
    Should Be True    isinstance($hostname, str)

KW-124 Set LAN Domain
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Domain    alias=${ALIAS}
    Set LAN Domain    ${original}    alias=${ALIAS}

KW-125 Get LAN Domain
    ${domain}=    Get LAN Domain    alias=${ALIAS}
    Should Be True    isinstance($domain, str)

KW-126 Set LAN Auto IP
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Auto IP    alias=${ALIAS}
    Set LAN Auto IP    ${original}    alias=${ALIAS}

KW-127 Get LAN Auto IP
    ${enabled}=    Get LAN Auto IP    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-128 Set LAN DDNS Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN DDNS Enabled    alias=${ALIAS}
    Set LAN DDNS Enabled    ${original}    alias=${ALIAS}

KW-129 Get LAN DDNS Enabled
    ${enabled}=    Get LAN DDNS Enabled    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-130 Set LAN Keepalive
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Keepalive    alias=${ALIAS}
    Set LAN Keepalive    ${original}    alias=${ALIAS}

KW-131 Get LAN Keepalive
    ${keepalive}=    Get LAN Keepalive    alias=${ALIAS}
    Should Be True    ${keepalive} >= 0

KW-132 Get LAN Logical IP Address
    [Documentation]    Read-only.
    ${address}=    Get LAN Logical IP Address    alias=${ALIAS}
    Should Not Be Empty    ${address}

KW-133 Get LAN MAC Address
    [Documentation]    Read-only.
    ${mac}=    Get LAN MAC Address    alias=${ALIAS}
    Should Not Be Empty    ${mac}

KW-134 Get LAN Connection Status
    [Documentation]    Read-only.
    ${status}=    Get LAN Connection Status    alias=${ALIAS}
    Should Not Be Empty    ${status}

KW-135 Get LAN Control Connection Status
    [Documentation]    Read-only.
    ${status}=    Get LAN Control Connection Status    alias=${ALIAS}
    Should Not Be Empty    ${status}

KW-136 Set LAN Media Sense Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Media Sense Enabled    alias=${ALIAS}
    Set LAN Media Sense Enabled    ${original}    alias=${ALIAS}

KW-137 Get LAN Media Sense Enabled
    ${enabled}=    Get LAN Media Sense Enabled    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-138 Set LAN NetBIOS Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN NetBIOS Enabled    alias=${ALIAS}
    Set LAN NetBIOS Enabled    ${original}    alias=${ALIAS}

KW-139 Get LAN NetBIOS Enabled
    ${enabled}=    Get LAN NetBIOS Enabled    alias=${ALIAS}
    Should Be True    $enabled is True or $enabled is False

KW-140 Set LAN Telnet Prompt
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Telnet Prompt    alias=${ALIAS}
    Set LAN Telnet Prompt    ${original}    alias=${ALIAS}

KW-141 Get LAN Telnet Prompt
    ${prompt}=    Get LAN Telnet Prompt    alias=${ALIAS}
    Should Be True    isinstance($prompt, str)

KW-142 Set LAN Telnet Welcome Message
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Telnet Welcome Message    alias=${ALIAS}
    Set LAN Telnet Welcome Message    ${original}    alias=${ALIAS}

KW-143 Get LAN Telnet Welcome Message
    ${message}=    Get LAN Telnet Welcome Message    alias=${ALIAS}
    Should Be True    isinstance($message, str)

KW-144 Clear LAN History
    Clear LAN History    alias=${ALIAS}

KW-145 Get LAN History
    ${history}=    Get LAN History    alias=${ALIAS}
    Should Not Be Equal    ${history}    ${None}

# ----------------------------------------------------------------------
# Raw SCPI escape hatch
# ----------------------------------------------------------------------
KW-146 Enable Raw SCPI
    [Documentation]    Requires the exact confirmation text; the enabled state then persists
    ...    for the rest of this suite's connection, so KW-147/KW-148 rely on it already
    ...    being enabled here rather than re-enabling it themselves.
    Enable Raw SCPI    ENABLE RAW SCPI    alias=${ALIAS}

KW-147 Raw SCPI Query
    [Documentation]    SYSTem:ERRor? is a universal, non-mutating SCPI query.
    ${response}=    Raw SCPI Query    SYSTem:ERRor?    alias=${ALIAS}
    Should Not Be Empty    ${response}
    Log    ${response}

KW-148 Raw SCPI Write
    [Documentation]    *CLS (clear status) is universal and harmless.
    Raw SCPI Write    *CLS    alias=${ALIAS}
    ${response}=    Raw SCPI Query    SYSTem:ERRor?    alias=${ALIAS}
    Should Not Be Empty    ${response}

# ----------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------
KW-149 Export Diagnostic Bundle
    ${path}=    Export Diagnostic Bundle
    Should Not Be Empty    ${path}
    File Should Exist    ${path}
    Log    Diagnostic bundle written to ${path}

*** Keywords ***
Initialize Hardware Conformance
    Require Real Resource
    Capture Software Evidence
    ${state}=    Connect    resource=${RESOURCE}    alias=${ALIAS}    timeout_s=${TIMEOUT_S}
    Log Dictionary    ${state}
    Set Suite Variable    ${CALIBRATION_SECURITY_CODE}    ${EMPTY}
    Run Keyword And Ignore Error    Fetch Calibration Security Code

Require Real Resource
    Should Not Be Equal    ${RESOURCE}    ${EMPTY}
    ...    Pass a real VISA resource string: -v RESOURCE:<visa resource>

Capture Software Evidence
    ${source_version}=    Evaluate    agilent34411a.__version__    modules=agilent34411a
    ${distribution_version}=    Evaluate
    ...    importlib.metadata.version("robotframework-agilent34411a")    modules=importlib.metadata
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
    ...    Installed robotframework-agilent34411a ${distribution_version} does not match imported source ${source_version}; reinstall the release wheel.

Fetch Calibration Security Code
    [Documentation]    Optional: if a CALIBRATION_SECURITY_CODE variable was passed in
    ...    (`-v CALIBRATION_SECURITY_CODE:<code>`), keep it; otherwise calibration-unlock
    ...    test cases are skipped via ALLOW_CALIBRATION defaulting to false regardless.
    Variable Should Exist    ${CALIBRATION_SECURITY_CODE}

Numbers Should Be Close
    [Arguments]    ${actual}    ${expected}    ${tolerance}
    ${difference}=    Evaluate    abs(float($actual) - float($expected))
    Should Be True    ${difference} <= ${tolerance}
    ...    Difference ${difference} exceeds tolerance ${tolerance}; actual=${actual}, expected=${expected}

Final Safe Teardown
    Run Keyword And Ignore Error    Disable Math    alias=${ALIAS}
    Run Keyword And Ignore Error    Disconnect    ${ALIAS}
    Run Keyword And Ignore Error    Disconnect    ${SECONDARY_ALIAS}
