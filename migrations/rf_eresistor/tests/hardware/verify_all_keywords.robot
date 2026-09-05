*** Settings ***
Documentation     RFDS-019 real-hardware conformance: exercises every public keyword of
...               rf_eresistor.EResistorLibrary against a physical OpenBench E-Resistor board
...               and verifies its response. Does not run automatically in CI (Force Tags
...               "hardware"; exclude with `--exclude hardware` in automated pipelines).
...
...               Requires HOST (see Variables below) — there is no safe default IP, so
...               Suite Setup fails immediately with a clear message if it is left at its
...               placeholder value.
...
...               Every channel stays at mask 0000 (open) for the whole suite unless
...               ALLOW_ACTIVATE is set — setting a mask/resistance/temperature activates a
...               MOSFET branch and can drive current through whatever is wired to that
...               channel (this driver's own README: "Do not connect a DUT until you have
...               run the read-only identity example and verified the channel/mask mapping
...               on your hardware"). Discovery keywords scan the network and are separately
...               gated behind ALLOW_DISCOVERY, off by default, since a subnet scan is
...               disruptive/unexpected default behavior even though it isn't physically
...               hazardous. Test Teardown and Suite Teardown always attempt to reopen every
...               channel regardless of how a test case left the board.
Library           rf_eresistor.EResistorLibrary    host=${HOST}
Library           Collections
Library           OperatingSystem
Suite Setup       Initialize Hardware Conformance
Suite Teardown    Final Safe Teardown
Test Setup        Prepare Board For Keyword Test
Test Teardown     Per Test Safe Teardown
Force Tags        hardware    eresistor    keyword-conformance

*** Variables ***
${HOST}                     0.0.0.0
${TEST_CHANNEL}             ${1}
${ALLOW_ACTIVATE}           ${FALSE}
${ALLOW_DISCOVERY}          ${FALSE}
${DISCOVERY_SUBNET}         ${EMPTY}
${EXPECTED_DRIVER_VERSION}    26.03

*** Test Cases ***
# ----------------------------------------------------------------------
# Connection (device-specific and RFDS-002 generic)
# ----------------------------------------------------------------------
KW-001 Connect To EResistor
    Disconnect From EResistor
    ${identity}=    Connect To EResistor    all_off_on_connect=${TRUE}
    Should Not Be Empty    ${identity}

KW-002 Disconnect From EResistor
    [Documentation]    Reconnects immediately afterward — this suite's single library
    ...    instance is shared across every remaining test case.
    Disconnect From EResistor
    ${connected}=    Is Connected
    Should Be Equal    ${connected}    ${FALSE}
    Connect To EResistor    all_off_on_connect=${TRUE}
    ${connected}=    Is Connected
    Should Be Equal    ${connected}    ${TRUE}

KW-003 E-Resistor Should Be Connected
    E-Resistor Should Be Connected

KW-004 Connect
    ${state}=    Connect    resource=${HOST}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[transport]    scpi_tcp

KW-005 Disconnect
    Disconnect
    ${connected}=    Is Connected
    Should Be Equal    ${connected}    ${FALSE}
    Connect To EResistor    all_off_on_connect=${TRUE}

KW-006 Is Connected
    ${connected}=    Is Connected
    Should Be Equal    ${connected}    ${TRUE}

KW-007 Get Connection State
    ${state}=    Get Connection State    refresh=${TRUE}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[communication_ok]    ${TRUE}
    Log Dictionary    ${state}

KW-008 Check Communication
    ${ok}=    Check Communication
    Should Be Equal    ${ok}    ${TRUE}

KW-009 Get Identity
    ${identity}=    Get Identity
    Should Not Be Empty    ${identity}

KW-010 Get EResistor Identity
    ${identity}=    Get EResistor Identity
    Should Not Be Empty    ${identity}
    Log    ${identity}

KW-011 Ping EResistor
    ${ok}=    Ping EResistor
    Should Be True    $ok is True or $ok is False

KW-012 Identify EResistor
    [Documentation]    Blinks the board's identify LED briefly — physically benign.
    ${response}=    Identify EResistor    duration_s=${1.0}
    Should Not Be Empty    ${response}

KW-013 Get EResistor Information
    ${info}=    Get EResistor Information
    Dictionary Should Contain Key    ${info}    identity
    Dictionary Should Contain Key    ${info}    serial
    Dictionary Should Contain Key    ${info}    firmware_version
    Log Dictionary    ${info}

# ----------------------------------------------------------------------
# Raw SCPI / status / errors
# ----------------------------------------------------------------------
KW-014 Send EResistor SCPI Query
    [Documentation]    SYST:ERR? is a universal, non-mutating SCPI query.
    ${response}=    Send EResistor SCPI Query    SYST:ERR?
    Should Not Be Empty    ${response}

KW-015 Get EResistor Status
    ${status}=    Get EResistor Status
    Should Be True    isinstance($status, dict)
    Log Dictionary    ${status}

KW-016 Get EResistor Error
    ${error}=    Get EResistor Error
    Should Be True    isinstance($error, str)

KW-017 Clear EResistor Errors
    ${response}=    Clear EResistor Errors
    Should Be True    isinstance($response, str)

# ----------------------------------------------------------------------
# Masks (mutating keywords gated behind ALLOW_ACTIVATE)
# ----------------------------------------------------------------------
KW-018 Set EResistor Mask
    Skip If    not ${ALLOW_ACTIVATE}    Set ALLOW_ACTIVATE:true to exercise Set EResistor Mask.
    Set EResistor Mask    ${TEST_CHANNEL}    0001
    EResistor Mask Should Be    ${TEST_CHANNEL}    0001
    Set EResistor Mask    ${TEST_CHANNEL}    0000

KW-019 Get EResistor Mask
    ${mask}=    Get EResistor Mask    ${TEST_CHANNEL}
    Should Not Be Empty    ${mask}

KW-020 Get All EResistor Masks
    ${masks}=    Get All EResistor Masks
    Length Should Be    ${masks}    8

KW-021 Set All EResistor Masks
    Skip If    not ${ALLOW_ACTIVATE}    Set ALLOW_ACTIVATE:true to exercise Set All EResistor Masks.
    ${zeros}=    Create List    0000    0000    0000    0000    0000    0000    0000    0000
    ${result}=    Set All EResistor Masks    @{zeros}
    Length Should Be    ${result}    8

KW-022 Set Selected EResistor Masks
    Skip If    not ${ALLOW_ACTIVATE}    Set ALLOW_ACTIVATE:true to exercise Set Selected EResistor Masks.
    ${selected}=    Create Dictionary    ${TEST_CHANNEL}=0001
    Set Selected EResistor Masks    ${selected}
    EResistor Mask Should Be    ${TEST_CHANNEL}    0001
    ${open}=    Create Dictionary    ${TEST_CHANNEL}=0000
    Set Selected EResistor Masks    ${open}

KW-023 Open All EResistor Channels
    Open All EResistor Channels
    ${masks}=    Get All EResistor Masks
    FOR    ${channel}    ${mask}    IN    &{masks}
        Should Be Equal    ${mask}    0000
    END

KW-024 EResistor Mask Should Be
    EResistor Mask Should Be    ${TEST_CHANNEL}    0000

# ----------------------------------------------------------------------
# Calibration (download/save/load are local-file-safe; never sets hardware)
# ----------------------------------------------------------------------
KW-025 Download EResistor Calibration
    ${calibration}=    Download EResistor Calibration
    Should Be True    isinstance($calibration, dict)
    Set Suite Variable    ${HAVE_CALIBRATION}    ${TRUE}

KW-026 Download EResistor Channel Calibration
    ${calibration}=    Download EResistor Channel Calibration    ${TEST_CHANNEL}
    Should Be True    isinstance($calibration, dict)

KW-027 Save EResistor Calibration
    ${path}=    Join Path    ${OUTPUT_DIR}    calibration_roundtrip.json
    Save EResistor Calibration    ${path}
    File Should Exist    ${path}
    Set Suite Variable    ${CALIBRATION_FILE}    ${path}

KW-028 Load EResistor Calibration
    [Documentation]    Round-trips the calibration downloaded and saved above — always safe,
    ...    never writes to the device.
    ${calibration}=    Load EResistor Calibration    ${CALIBRATION_FILE}
    Should Be True    isinstance($calibration, dict)

# ----------------------------------------------------------------------
# Resistance solver (local computation; Set keywords gated)
# ----------------------------------------------------------------------
KW-029 Build EResistor Resistance Cache
    Build EResistor Resistance Cache

KW-030 Calculate EResistor Resistance
    ${ohms}=    Calculate EResistor Resistance    ${TEST_CHANNEL}    0000
    Should Be True    isinstance($ohms, (int, float))

KW-031 Find Closest EResistor Resistance
    ${result}=    Find Closest EResistor Resistance    ${TEST_CHANNEL}    ${1000.0}
    Dictionary Should Contain Key    ${result}    mask

KW-032 Set EResistor Resistance
    Skip If    not ${ALLOW_ACTIVATE}    Set ALLOW_ACTIVATE:true to exercise Set EResistor Resistance.
    ${result}=    Set EResistor Resistance    ${TEST_CHANNEL}    ${1000.0}
    Dictionary Should Contain Key    ${result}    mask
    Set EResistor Mask    ${TEST_CHANNEL}    0000

KW-033 Set Multiple EResistor Resistances
    Skip If    not ${ALLOW_ACTIVATE}    Set ALLOW_ACTIVATE:true to exercise Set Multiple EResistor Resistances.
    ${values}=    Create Dictionary    ${TEST_CHANNEL}=${1000.0}
    ${results}=    Set Multiple EResistor Resistances    ${values}
    Length Should Be    ${results}    1
    Set EResistor Mask    ${TEST_CHANNEL}    0000

# ----------------------------------------------------------------------
# Temperature tables (Load keywords are local-file-safe; Set is gated)
# ----------------------------------------------------------------------
KW-034 Load EResistor Temperature Table
    ${path}=    Join Path    ${OUTPUT_DIR}    temp_table_ch.csv
    Create File    ${path}    temperature_c,dwell_s\n25.0,0\n50.0,0\n
    ${table}=    Load EResistor Temperature Table    ${TEST_CHANNEL}    ${path}
    Dictionary Should Contain Key    ${table}    source

KW-035 Load EResistor Temperature Table For All Channels
    ${path}=    Join Path    ${OUTPUT_DIR}    temp_table_all.csv
    Create File    ${path}    temperature_c,dwell_s\n25.0,0\n50.0,0\n
    ${table}=    Load EResistor Temperature Table For All Channels    ${path}
    Dictionary Should Contain Key    ${table}    source

KW-036 Set EResistor Temperature
    Skip If    not ${ALLOW_ACTIVATE}    Set ALLOW_ACTIVATE:true to exercise Set EResistor Temperature.
    ${result}=    Set EResistor Temperature    ${TEST_CHANNEL}    ${25.0}
    Dictionary Should Contain Key    ${result}    mask
    Set EResistor Mask    ${TEST_CHANNEL}    0000

# ----------------------------------------------------------------------
# Watchdog and metrics
# ----------------------------------------------------------------------
KW-037 Start EResistor Watchdog
    TRY
        Start EResistor Watchdog
    FINALLY
        Stop EResistor Watchdog
    END

KW-038 Stop EResistor Watchdog
    Stop EResistor Watchdog

KW-039 Get EResistor Metrics
    ${metrics}=    Get EResistor Metrics
    Should Be True    isinstance($metrics, dict)
    Log Dictionary    ${metrics}

# ----------------------------------------------------------------------
# Discovery (gated: network scanning is opt-in, off by default)
# ----------------------------------------------------------------------
KW-040 Discover EResistor Boards
    Skip If    not ${ALLOW_DISCOVERY}    Set ALLOW_DISCOVERY:true and DISCOVERY_SUBNET:<cidr> to exercise discovery.
    Skip If    "${DISCOVERY_SUBNET}" == "${EMPTY}"    DISCOVERY_SUBNET must be set (e.g. 192.168.0.0/24).
    ${boards}=    Discover EResistor Boards    ${DISCOVERY_SUBNET}    timeout=${0.25}
    Should Be True    isinstance($boards, list)

KW-041 Auto Discover EResistor Boards
    Skip If    not ${ALLOW_DISCOVERY}    Set ALLOW_DISCOVERY:true to exercise Auto Discover EResistor Boards.
    ${boards}=    Auto Discover EResistor Boards    timeout=${0.25}
    Should Be True    isinstance($boards, list)

# ----------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------
KW-042 Export Diagnostic Bundle
    ${path}=    Export Diagnostic Bundle
    Should Not Be Empty    ${path}
    File Should Exist    ${path}
    Log    Diagnostic bundle written to ${path}

*** Keywords ***
Initialize Hardware Conformance
    Require Real Host
    Capture Software Evidence
    ${identity}=    Connect To EResistor    all_off_on_connect=${TRUE}
    Log    Connected to ${identity}
    Open All EResistor Channels

Require Real Host
    [Documentation]    0.0.0.0 is never a real board address (PhidgetRelayConfigurationError-style
    ...    fast, clear failure instead of a confusing connection timeout).
    Should Not Be Equal As Strings    ${HOST}    0.0.0.0
    ...    Pass a real E-Resistor host: -v HOST:<ip-or-hostname>

Capture Software Evidence
    ${source_version}=    Evaluate    rf_eresistor.__version__    modules=rf_eresistor
    ${distribution_version}=    Evaluate
    ...    importlib.metadata.version("rf-eresistor")    modules=importlib.metadata
    ${robot_version}=    Evaluate    robot.__version__    modules=robot
    ${python_version}=    Evaluate    platform.python_version()    modules=platform
    Set Suite Metadata    Driver source version    ${source_version}
    Set Suite Metadata    Installed distribution version    ${distribution_version}
    Set Suite Metadata    Robot Framework version    ${robot_version}
    Set Suite Metadata    Python version    ${python_version}
    Log To Console
    ...    Driver source=${source_version}; installed=${distribution_version}; Robot=${robot_version}; Python=${python_version}
    Should Be Equal    ${source_version}    ${EXPECTED_DRIVER_VERSION}
    ...    Source package version ${source_version} does not match suite release ${EXPECTED_DRIVER_VERSION}.
    Should Be Equal    ${distribution_version}    ${source_version}
    ...    Installed rf-eresistor ${distribution_version} does not match imported source ${source_version}; reinstall the release wheel.

Prepare Board For Keyword Test
    ${connected}=    Is Connected
    IF    not ${connected}
        Connect To EResistor    all_off_on_connect=${TRUE}
    END
    Open All EResistor Channels

Per Test Safe Teardown
    Run Keyword And Ignore Error    Open All EResistor Channels

Final Safe Teardown
    Run Keyword And Ignore Error    Open All EResistor Channels
    Run Keyword And Ignore Error    Disconnect From EResistor
