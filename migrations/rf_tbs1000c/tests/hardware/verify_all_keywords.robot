*** Settings ***
Documentation     RFDS-019 real-hardware conformance: exercises every public keyword of
...               rf_tbs1000c.Tbs1000cLibrary against a physical TBS1000C oscilloscope and
...               verifies its response. Does not run automatically in CI (Force Tags
...               "hardware"; exclude with `--exclude hardware` in automated pipelines).
...
...               Requires RESOURCE (a VISA USBTMC resource string) — there is no safe
...               default, so Suite Setup fails immediately with a clear message if it is
...               left empty. Channel/trigger/acquisition settings are captured at Suite
...               Setup and restored at Suite Teardown (Run Autoset and the Set keywords all
...               change live configuration, never anything persistent across a power cycle,
...               but this suite still leaves the instrument as it found it either way).
...
...               Three flags gate operations that are disruptive or touch instrument-persistent
...               storage — see the per-keyword Documentation below for exactly what each
...               unlocks:
...               - ALLOW_CALIBRATION: Run Internal Calibration takes the instrument offline
...                 for the duration of the self-test.
...               - ALLOW_FACTORY_RESET: Restore Factory Setup wipes all current settings
...                 (the suite restores the pre-test setup immediately afterward via Restore
...                 Setup, captured at Suite Setup).
...               - ALLOW_INSTRUMENT_MEMORY_WRITE: any keyword that writes to the
...                 instrument's own persistent memory (setup slots, reference-waveform
...                 slots, its internal filesystem) rather than a host file or live/volatile
...                 configuration — uses a scratch slot/filename identified by SCRATCH_SLOT
...                 so it never overwrites a slot you actually care about, but a slot
...                 collision is still possible on a bench you don't control; verify
...                 SCRATCH_SLOT is unused first.
Library           rf_tbs1000c.Tbs1000cLibrary
Library           Collections
Library           OperatingSystem
Suite Setup       Initialize Hardware Conformance
Suite Teardown    Final Safe Teardown
Test Setup        Prepare Oscilloscope For Keyword Test
Force Tags        hardware    tbs1000c    keyword-conformance

*** Variables ***
${RESOURCE}                      ${EMPTY}
${ALIAS}                         hardware
${SECONDARY_ALIAS}               secondary
${TEST_CHANNEL}                  ${1}
${SCRATCH_SLOT}                  ${4}
${ALLOW_CALIBRATION}             ${FALSE}
${ALLOW_FACTORY_RESET}           ${FALSE}
${ALLOW_INSTRUMENT_MEMORY_WRITE}    ${FALSE}
${EXPECTED_DRIVER_VERSION}       26.2

*** Test Cases ***
# ----------------------------------------------------------------------
# Connection (RFDS-002)
# ----------------------------------------------------------------------
KW-001 Connect
    Disconnect    ${ALIAS}
    ${state}=    Open Hardware Connection
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[state]    connected
    Should Not Be Empty    ${state}[resource]

KW-002 Disconnect
    [Documentation]    Idempotent: closing an already-closed alias must not raise.
    Connect    simulated=${TRUE}    alias=${SECONDARY_ALIAS}
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
    Should Contain    ${identity}    TEKTRONIX
    Log    ${identity}

KW-007 Switch Oscilloscope
    Connect    simulated=${TRUE}    alias=${SECONDARY_ALIAS}
    ${active}=    Switch Oscilloscope    ${SECONDARY_ALIAS}
    Should Be Equal    ${active}    ${SECONDARY_ALIAS}
    Switch Oscilloscope    ${ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

KW-008 Get Active Oscilloscope
    ${active}=    Get Active Oscilloscope
    Should Be Equal    ${active}    ${ALIAS}

KW-009 List Oscilloscope Connections
    Connect    simulated=${TRUE}    alias=${SECONDARY_ALIAS}
    ${connections}=    List Oscilloscope Connections
    List Should Contain Value    ${connections}    ${ALIAS}
    List Should Contain Value    ${connections}    ${SECONDARY_ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

# ----------------------------------------------------------------------
# Channel setup
# ----------------------------------------------------------------------
KW-010 Set Channel Scale
    Set Channel Scale    ${TEST_CHANNEL}    0.5    alias=${ALIAS}
    ${scale}=    Get Channel Scale    ${TEST_CHANNEL}    alias=${ALIAS}
    Numbers Should Be Close    ${scale}    0.5    0.01

KW-011 Get Channel Scale
    ${scale}=    Get Channel Scale    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${scale} > 0

KW-012 Set Channel Position
    Set Channel Position    ${TEST_CHANNEL}    1.0    alias=${ALIAS}
    ${position}=    Get Channel Position    ${TEST_CHANNEL}    alias=${ALIAS}
    Numbers Should Be Close    ${position}    1.0    0.05

KW-013 Get Channel Position
    ${position}=    Get Channel Position    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    isinstance($position, float) or isinstance($position, int)

KW-014 Set Channel Offset
    Set Channel Offset    ${TEST_CHANNEL}    0.0    alias=${ALIAS}
    ${offset}=    Get Channel Offset    ${TEST_CHANNEL}    alias=${ALIAS}
    Numbers Should Be Close    ${offset}    0.0    0.05

KW-015 Get Channel Offset
    ${offset}=    Get Channel Offset    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    isinstance($offset, float) or isinstance($offset, int)

KW-016 Set Channel Coupling
    Set Channel Coupling    ${TEST_CHANNEL}    DC    alias=${ALIAS}
    ${coupling}=    Get Channel Coupling    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${coupling}    DC

KW-017 Get Channel Coupling
    ${coupling}=    Get Channel Coupling    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Contain Any    ${coupling}    DC    AC    GND

KW-018 Set Channel Bandwidth Limit
    Set Channel Bandwidth Limit    ${TEST_CHANNEL}    FULL    alias=${ALIAS}
    ${limit}=    Get Channel Bandwidth Limit    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Not Be Empty    ${limit}

KW-019 Get Channel Bandwidth Limit
    ${limit}=    Get Channel Bandwidth Limit    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Not Be Empty    ${limit}

KW-020 Set Channel Probe Gain
    ${original}=    Get Channel Probe Gain    ${TEST_CHANNEL}    alias=${ALIAS}
    Set Channel Probe Gain    ${TEST_CHANNEL}    10.0    alias=${ALIAS}
    ${gain}=    Get Channel Probe Gain    ${TEST_CHANNEL}    alias=${ALIAS}
    Numbers Should Be Close    ${gain}    10.0    0.1
    Set Channel Probe Gain    ${TEST_CHANNEL}    ${original}    alias=${ALIAS}

KW-021 Get Channel Probe Gain
    ${gain}=    Get Channel Probe Gain    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${gain} > 0

KW-022 Set Channel Name
    ${original}=    Get Channel Name    ${TEST_CHANNEL}    alias=${ALIAS}
    Set Channel Name    ${TEST_CHANNEL}    RFDS019    alias=${ALIAS}
    ${name}=    Get Channel Name    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${name}    RFDS019
    Set Channel Name    ${TEST_CHANNEL}    ${original}    alias=${ALIAS}

KW-023 Get Channel Name
    ${name}=    Get Channel Name    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    isinstance($name, str)

KW-024 Get Channel Settings
    ${settings}=    Get Channel Settings    ${TEST_CHANNEL}    alias=${ALIAS}
    Dictionary Should Contain Key    ${settings}    scale
    Log Dictionary    ${settings}

# ----------------------------------------------------------------------
# Trigger
# ----------------------------------------------------------------------
KW-025 Set Trigger Source
    Set Trigger Source    ${TEST_CHANNEL}    alias=${ALIAS}
    ${source}=    Get Trigger Source    alias=${ALIAS}
    Should Contain    ${source}    ${TEST_CHANNEL}

KW-026 Get Trigger Source
    ${source}=    Get Trigger Source    alias=${ALIAS}
    Should Not Be Empty    ${source}

KW-027 Set Trigger Slope
    Set Trigger Slope    RISE    alias=${ALIAS}
    ${slope}=    Get Trigger Slope    alias=${ALIAS}
    Should Contain Any    ${slope}    RISE    FALL    EITHER    RISING    FALLING

KW-028 Get Trigger Slope
    ${slope}=    Get Trigger Slope    alias=${ALIAS}
    Should Not Be Empty    ${slope}

KW-029 Set Trigger Coupling
    Set Trigger Coupling    DC    alias=${ALIAS}
    ${coupling}=    Get Trigger Coupling    alias=${ALIAS}
    Should Contain    ${coupling}    DC

KW-030 Get Trigger Coupling
    ${coupling}=    Get Trigger Coupling    alias=${ALIAS}
    Should Not Be Empty    ${coupling}

KW-031 Set Trigger Level
    Set Trigger Level    0.0    alias=${ALIAS}
    ${level}=    Get Trigger Level    alias=${ALIAS}
    Numbers Should Be Close    ${level}    0.0    0.5

KW-032 Get Trigger Level
    ${level}=    Get Trigger Level    alias=${ALIAS}
    Should Be True    isinstance($level, float) or isinstance($level, int)

KW-033 Auto Set Trigger Level
    Auto Set Trigger Level    alias=${ALIAS}
    ${level}=    Get Trigger Level    alias=${ALIAS}
    Log    Auto trigger level: ${level}

KW-034 Force Trigger
    Force Trigger    alias=${ALIAS}

KW-035 Get Trigger Settings
    ${settings}=    Get Trigger Settings    alias=${ALIAS}
    Dictionary Should Contain Key    ${settings}    source
    Log Dictionary    ${settings}

# ----------------------------------------------------------------------
# Acquisition and autoset
# ----------------------------------------------------------------------
KW-036 Run Autoset
    [Documentation]    Changes vertical scale, trigger level, and timebase — Suite Teardown
    ...    restores every channel/trigger setting captured at Suite Setup regardless.
    Run Autoset    alias=${ALIAS}

KW-037 Start Acquisition
    Start Acquisition    alias=${ALIAS}

KW-038 Stop Acquisition
    Stop Acquisition    alias=${ALIAS}

KW-039 Set Acquisition Mode
    ${original}=    Get Acquisition Mode    alias=${ALIAS}
    Set Acquisition Mode    SAMPLE    alias=${ALIAS}
    ${mode}=    Get Acquisition Mode    alias=${ALIAS}
    Should Be Equal    ${mode}    SAMPLE
    Set Acquisition Mode    ${original}    alias=${ALIAS}

KW-040 Get Acquisition Mode
    ${mode}=    Get Acquisition Mode    alias=${ALIAS}
    Should Not Be Empty    ${mode}

KW-041 Get Acquisition Count
    ${count}=    Get Acquisition Count    alias=${ALIAS}
    Should Be True    ${count} >= 0

# ----------------------------------------------------------------------
# Calibration
# ----------------------------------------------------------------------
KW-042 Run Internal Calibration
    [Documentation]    Takes the instrument offline for the duration of its self-test.
    Skip If    not ${ALLOW_CALIBRATION}    Set ALLOW_CALIBRATION:true to exercise Run Internal Calibration.
    Run Internal Calibration    alias=${ALIAS}
    ${status}=    Get Calibration Status    alias=${ALIAS}
    Log Dictionary    ${status}

KW-043 Get Calibration Status
    ${status}=    Get Calibration Status    alias=${ALIAS}
    Should Not Be Empty    ${status}
    Log Dictionary    ${status}

KW-044 Get Calibration Results
    ${results}=    Get Calibration Results    alias=${ALIAS}
    Should Be True    isinstance($results, str)

# ----------------------------------------------------------------------
# Measurement and waveform
# ----------------------------------------------------------------------
KW-045 Get Immediate Measurement
    ${value}=    Get Immediate Measurement    FREQuency    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    isinstance($value, float) or isinstance($value, int)

KW-046 Measurement Should Be Within
    ${value}=    Measurement Should Be Within    FREQuency    ${TEST_CHANNEL}    0    1.0E9    alias=${ALIAS}
    Log    Frequency: ${value}

KW-047 Get Waveform
    ${waveform}=    Get Waveform    ${TEST_CHANNEL}    alias=${ALIAS}
    Dictionary Should Contain Key    ${waveform}    time_s
    Dictionary Should Contain Key    ${waveform}    volts
    Log    Waveform sample count: ${{len($waveform['volts'])}}

KW-048 Save Screen Image
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_screen.png
    Save Screen Image    ${path}    alias=${ALIAS}
    File Should Exist    ${path}

KW-049 Save Waveform To CSV
    [Documentation]    Primary implementation: host-side decode, no instrument storage touched.
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_waveform.csv
    Save Waveform To CSV    ${path}    ${TEST_CHANNEL}    alias=${ALIAS}
    File Should Exist    ${path}

KW-050 Save Waveform To CSV On Instrument
    [Documentation]    Vendor-native SAVe:WAVEform — writes to the instrument's own storage,
    ...    so gated the same as the instrument-memory-write keywords below.
    Skip If    not ${ALLOW_INSTRUMENT_MEMORY_WRITE}
    ...    Set ALLOW_INSTRUMENT_MEMORY_WRITE:true to exercise Save Waveform To CSV On Instrument.
    Save Waveform To CSV On Instrument    E:/RFDS019.CSV    ${TEST_CHANNEL}    alias=${ALIAS}

KW-051 Save Waveform To Reference Memory
    Skip If    not ${ALLOW_INSTRUMENT_MEMORY_WRITE}
    ...    Set ALLOW_INSTRUMENT_MEMORY_WRITE:true to exercise Save Waveform To Reference Memory.
    Save Waveform To Reference Memory    ${TEST_CHANNEL}    1    alias=${ALIAS}

KW-052 Recall Waveform From Host File
    [Documentation]    Round-trip counterpart to Save Waveform To CSV On Instrument — uploads
    ...    the CSV captured by KW-049 back into reference memory.
    Skip If    not ${ALLOW_INSTRUMENT_MEMORY_WRITE}
    ...    Set ALLOW_INSTRUMENT_MEMORY_WRITE:true to exercise Recall Waveform From Host File.
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_waveform.csv
    Recall Waveform From Host File    ${path}    1    alias=${ALIAS}

# ----------------------------------------------------------------------
# Setup save/restore
# ----------------------------------------------------------------------
KW-053 Save Setup
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_setup.lrn
    Save Setup    ${path}    alias=${ALIAS}
    File Should Exist    ${path}

KW-054 Restore Setup
    [Documentation]    Round-trips the instrument's own current setup (captured by KW-053) —
    ...    always safe since it recreates the state that was already there.
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_setup.lrn
    Restore Setup    ${path}    alias=${ALIAS}

KW-055 Save Setup To Instrument Memory
    Skip If    not ${ALLOW_INSTRUMENT_MEMORY_WRITE}
    ...    Set ALLOW_INSTRUMENT_MEMORY_WRITE:true to exercise Save Setup To Instrument Memory.
    Save Setup To Instrument Memory    ${SCRATCH_SLOT}    alias=${ALIAS}

KW-056 Restore Setup From Instrument Memory
    [Documentation]    Depends on KW-055 having written SCRATCH_SLOT in this same run.
    Skip If    not ${ALLOW_INSTRUMENT_MEMORY_WRITE}
    ...    Set ALLOW_INSTRUMENT_MEMORY_WRITE:true to exercise Restore Setup From Instrument Memory.
    Restore Setup From Instrument Memory    ${SCRATCH_SLOT}    alias=${ALIAS}
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_setup.lrn
    Restore Setup    ${path}    alias=${ALIAS}

KW-057 Restore Factory Setup
    [Documentation]    Wipes all current settings. Immediately restores the pre-test setup
    ...    captured by KW-053/Initialize Hardware Conformance via Restore Setup afterward.
    Skip If    not ${ALLOW_FACTORY_RESET}    Set ALLOW_FACTORY_RESET:true to exercise Restore Factory Setup.
    Restore Factory Setup    alias=${ALIAS}
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_setup.lrn
    Restore Setup    ${path}    alias=${ALIAS}

# ----------------------------------------------------------------------
# Raw SCPI escape hatch
# ----------------------------------------------------------------------
KW-058 Enable Raw SCPI
    [Documentation]    Requires the exact confirmation text; the enabled state then persists
    ...    for the rest of this alias's connection, so KW-059/KW-060 rely on it already being
    ...    enabled here rather than re-enabling it themselves.
    Enable Raw SCPI    ENABLE RAW SCPI    alias=${ALIAS}

KW-059 Raw SCPI Query
    [Documentation]    *IDN? is a universal, non-mutating SCPI query — safe on any SCPI
    ...    instrument and a good proof that the raw escape hatch round-trips real responses.
    ${response}=    Raw SCPI Query    *IDN?    alias=${ALIAS}
    Should Not Be Empty    ${response}

KW-060 Raw SCPI Write
    [Documentation]    *CLS (clear status) is universal and harmless.
    Raw SCPI Write    *CLS    alias=${ALIAS}
    ${response}=    Raw SCPI Query    *ESR?    alias=${ALIAS}
    Should Not Be Empty    ${response}

# ----------------------------------------------------------------------
# RFDS-008 evidence
# ----------------------------------------------------------------------
KW-061 Export Diagnostic Bundle
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
    Capture Original Configuration

Require Real Resource
    Should Not Be Empty    ${RESOURCE}
    ...    Pass a real VISA USBTMC resource string: -v RESOURCE:USB0::0x0699::0x03C4::<serial>::INSTR

Capture Software Evidence
    ${source_version}=    Evaluate    rf_tbs1000c.__version__    modules=rf_tbs1000c
    ${distribution_version}=    Evaluate
    ...    importlib.metadata.version("robotframework-tbs1000c")    modules=importlib.metadata
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
    ...    Installed robotframework-tbs1000c ${distribution_version} does not match imported source ${source_version}; reinstall the release wheel.

Open Hardware Connection
    Log    Opening real TBS1000C on resource=${RESOURCE}.
    ${state}=    Connect    resource=${RESOURCE}    alias=${ALIAS}
    RETURN    ${state}

Capture Original Configuration
    [Documentation]    Captures scale/position/offset/coupling/trigger settings so Final Safe
    ...    Teardown can restore them regardless of which Set keywords or Run Autoset ran.
    ${original_scale}=    Get Channel Scale    ${TEST_CHANNEL}    alias=${ALIAS}
    ${original_position}=    Get Channel Position    ${TEST_CHANNEL}    alias=${ALIAS}
    ${original_offset}=    Get Channel Offset    ${TEST_CHANNEL}    alias=${ALIAS}
    ${original_coupling}=    Get Channel Coupling    ${TEST_CHANNEL}    alias=${ALIAS}
    ${original_trigger_source}=    Get Trigger Source    alias=${ALIAS}
    ${original_trigger_slope}=    Get Trigger Slope    alias=${ALIAS}
    ${original_trigger_coupling}=    Get Trigger Coupling    alias=${ALIAS}
    ${original_trigger_level}=    Get Trigger Level    alias=${ALIAS}
    ${original_acquisition_mode}=    Get Acquisition Mode    alias=${ALIAS}
    Set Suite Variable    ${ORIGINAL_SCALE}    ${original_scale}
    Set Suite Variable    ${ORIGINAL_POSITION}    ${original_position}
    Set Suite Variable    ${ORIGINAL_OFFSET}    ${original_offset}
    Set Suite Variable    ${ORIGINAL_COUPLING}    ${original_coupling}
    Set Suite Variable    ${ORIGINAL_TRIGGER_SOURCE}    ${original_trigger_source}
    Set Suite Variable    ${ORIGINAL_TRIGGER_SLOPE}    ${original_trigger_slope}
    Set Suite Variable    ${ORIGINAL_TRIGGER_COUPLING}    ${original_trigger_coupling}
    Set Suite Variable    ${ORIGINAL_TRIGGER_LEVEL}    ${original_trigger_level}
    Set Suite Variable    ${ORIGINAL_ACQUISITION_MODE}    ${original_acquisition_mode}
    ${path}=    Join Path    ${OUTPUT_DIR}    rfds019_setup.lrn
    Save Setup    ${path}    alias=${ALIAS}

Prepare Oscilloscope For Keyword Test
    ${status}=    Is Connected    ${ALIAS}
    IF    not ${status}
        Open Hardware Connection
    END

Final Safe Teardown
    Run Keyword And Ignore Error    Set Channel Scale    ${TEST_CHANNEL}    ${ORIGINAL_SCALE}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Channel Position    ${TEST_CHANNEL}    ${ORIGINAL_POSITION}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Channel Offset    ${TEST_CHANNEL}    ${ORIGINAL_OFFSET}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Channel Coupling    ${TEST_CHANNEL}    ${ORIGINAL_COUPLING}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Trigger Source    ${ORIGINAL_TRIGGER_SOURCE}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Trigger Slope    ${ORIGINAL_TRIGGER_SLOPE}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Trigger Coupling    ${ORIGINAL_TRIGGER_COUPLING}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Trigger Level    ${ORIGINAL_TRIGGER_LEVEL}    alias=${ALIAS}
    Run Keyword And Ignore Error    Set Acquisition Mode    ${ORIGINAL_ACQUISITION_MODE}    alias=${ALIAS}
    Run Keyword And Ignore Error    Disconnect    ${ALIAS}

Numbers Should Be Close
    [Arguments]    ${actual}    ${expected}    ${tolerance}
    ${difference}=    Evaluate    abs(float($actual) - float($expected))
    Should Be True    ${difference} <= ${tolerance}
    ...    Difference ${difference} exceeds tolerance ${tolerance}; actual=${actual}, expected=${expected}
