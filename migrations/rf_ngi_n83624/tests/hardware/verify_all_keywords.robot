*** Settings ***
Documentation     RFDS-019 real-hardware conformance: exercises every public keyword of
...               rf_ngi_n83624.NGI_N83624Library against a physical NGI N83624 24-channel
...               cell simulator over TCP and verifies its response. Does not run
...               automatically in CI (Force Tags "hardware"; exclude with `--exclude
...               hardware` in automated pipelines).
...
...               Connects by TCP (HOST/PORT, defaults 192.168.0.123:7000 per the vendor
...               manual) since that is the safest, most reliable interface documented for
...               this instrument (the driver's own README recommends TCP over UDP for
...               safety-critical control). Two emulator-only keywords (Set Emulator Channel
...               Measurement, Get Emulator Command Log) are exercised against a secondary
...               in-process emulator session (RFDS-019 section 11.1 approved-simulator
...               allowance) since they are documented to raise SessionStateError against any
...               real session by design — that refusal is itself what KW-060/KW-061 verify.
...
...               Every channel stays disarmed/output-off for the whole suite unless
...               ALLOW_OUTPUT_ON is set, and settings that can "break communication" per the
...               driver's own docstrings (IP address, serial baud rate, LAN connection type —
...               reachable only through Raw SCPI here, since NGI_N83624 does not expose them
...               as typed keywords) are never touched. See per-keyword Documentation below
...               for exactly what each flag unlocks. Test Teardown disarms and switches off
...               every channel on the primary connection regardless of test outcome; Suite
...               Teardown additionally closes every connection this suite opened.
...
...               Test cases run in the fixed order below (this suite does not support
...               `--randomize`): KW-005 (Open N83624 Emulator) is what creates EMULATOR_ALIAS,
...               reused read-only by KW-006/007/008/060/061 later. KW-002/KW-003 are tagged
...               `udp`; exclude them with `--exclude udp` on a bench/bridge that only proxies
...               TCP.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${FALSE}
Library           Collections
Library           OperatingSystem
Suite Setup       Initialize Hardware Conformance
Suite Teardown    Final Safe Teardown
Test Setup        Prepare Bench For Keyword Test
Test Teardown     Per Test Safe Teardown
Force Tags        hardware    ngi_n83624    keyword-conformance

*** Variables ***
${HOST}                      192.168.0.123
${PORT}                      ${7000}
${TIMEOUT}                   ${3.0}
${SERIAL_PORT}               ${EMPTY}
${ALIAS}                     bench
${SECONDARY_ALIAS}           secondary
${EMULATOR_ALIAS}            emu_check
${TEST_CHANNEL}              ${1}
${ALLOW_OUTPUT_ON}            ${FALSE}
${MAX_VOLTAGE_V}             ${5.0}
${MAX_CURRENT_MA}            ${200.0}
${SAFE_TEST_VOLTAGE}         ${0.0}
${SAFE_TEST_CURRENT_MA}      ${50.0}
${EXPECTED_RELEASE_VERSION}    26.02

*** Test Cases ***
# ----------------------------------------------------------------------
# Connection management
# ----------------------------------------------------------------------
KW-001 Open N83624 TCP Connection
    [Documentation]    Reopens the primary bench connection and verifies the resulting alias.
    Close N83624 Connection    ${ALIAS}
    ${opened}=    Open N83624 TCP Connection    ${ALIAS}    host=${HOST}    port=${PORT}
    ...    timeout=${TIMEOUT}    max_voltage_v=${MAX_VOLTAGE_V}    max_current_ma=${MAX_CURRENT_MA}
    Should Be Equal    ${opened}    ${ALIAS}

KW-002 Open N83624 UDP Connection
    [Documentation]    Opens and immediately closes a UDP session on the multi-channel port
    ...    7000 — a secondary, non-primary alias so it cannot disturb the TCP bench connection.
    [Tags]    udp
    ${opened}=    Open N83624 UDP Connection    ${SECONDARY_ALIAS}    host=${HOST}    port=${7000}
    ...    timeout=${TIMEOUT}
    Should Be Equal    ${opened}    ${SECONDARY_ALIAS}
    Close N83624 Connection    ${SECONDARY_ALIAS}

KW-003 Open N83624 Channel UDP Connection
    [Documentation]    Opens the channel-specific UDP port for TEST_CHANNEL (7000+channel).
    [Tags]    udp
    ${opened}=    Open N83624 Channel UDP Connection    ${SECONDARY_ALIAS}    ${HOST}    ${TEST_CHANNEL}
    ...    timeout=${TIMEOUT}
    Should Be Equal    ${opened}    ${SECONDARY_ALIAS}
    Close N83624 Connection    ${SECONDARY_ALIAS}

KW-004 Open N83624 Serial Connection
    [Documentation]    Skipped unless SERIAL_PORT is set — most benches only expose TCP/UDP.
    Skip If    "${SERIAL_PORT}" == "${EMPTY}"    Set -v SERIAL_PORT:<port> to exercise this keyword.
    ${opened}=    Open N83624 Serial Connection    ${SECONDARY_ALIAS}    ${SERIAL_PORT}
    Should Be Equal    ${opened}    ${SECONDARY_ALIAS}
    Close N83624 Connection    ${SECONDARY_ALIAS}

KW-005 Open N83624 Emulator
    [Documentation]    The approved-simulator session used by KW-060/KW-061 (see suite
    ...    Documentation) — opened here and left open for the rest of the suite, closed in
    ...    Final Safe Teardown.
    ${opened}=    Open N83624 Emulator    ${EMULATOR_ALIAS}    max_voltage_v=${MAX_VOLTAGE_V}
    ...    max_current_ma=${MAX_CURRENT_MA}
    Should Be Equal    ${opened}    ${EMULATOR_ALIAS}

KW-006 Switch N83624 Connection
    Switch N83624 Connection    ${EMULATOR_ALIAS}
    ${active}=    Get Active N83624 Connection
    Should Be Equal    ${active}    ${EMULATOR_ALIAS}
    Switch N83624 Connection    ${ALIAS}

KW-007 Get Active N83624 Connection
    ${active}=    Get Active N83624 Connection
    Should Be Equal    ${active}    ${ALIAS}

KW-008 List N83624 Connections
    ${connections}=    List N83624 Connections
    List Should Contain Value    ${connections}    ${ALIAS}
    List Should Contain Value    ${connections}    ${EMULATOR_ALIAS}

KW-009 Close N83624 Connection
    [Documentation]    Closes a throwaway secondary alias — the primary bench connection is
    ...    never the target here, so later test cases are unaffected. Uses the emulator
    ...    (not UDP) for the throwaway session so this test has no dependency on the bench's
    ...    UDP reachability, unlike the connection type it's closing being the point.
    Open N83624 Emulator    ${SECONDARY_ALIAS}
    Close N83624 Connection    ${SECONDARY_ALIAS}
    ${connections}=    List N83624 Connections
    List Should Not Contain Value    ${connections}    ${SECONDARY_ALIAS}

KW-010 Close All N83624 Connections
    [Documentation]    Closes every open alias including the primary bench connection, then
    ...    reopens everything this suite depends on so later tests are unaffected.
    Close All N83624 Connections
    ${connections}=    List N83624 Connections
    Length Should Be    ${connections}    0
    Open N83624 TCP Connection    ${ALIAS}    host=${HOST}    port=${PORT}    timeout=${TIMEOUT}
    ...    max_voltage_v=${MAX_VOLTAGE_V}    max_current_ma=${MAX_CURRENT_MA}
    Open N83624 Emulator    ${EMULATOR_ALIAS}    max_voltage_v=${MAX_VOLTAGE_V}    max_current_ma=${MAX_CURRENT_MA}
    Switch N83624 Connection    ${ALIAS}

KW-011 Identify N83624
    ${idn}=    Identify N83624
    Should Not Be Empty    ${idn}
    Log    ${idn}

# ----------------------------------------------------------------------
# RFDS-002 generic connection keywords
# ----------------------------------------------------------------------
KW-012 Connect
    [Documentation]    RFDS-002 generic Connect is idempotent against an alias already
    ...    connected to the same resource — proven by calling it against the live bench alias.
    ${state}=    Connect    resource=${HOST}    alias=${ALIAS}
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}

KW-013 Disconnect
    [Documentation]    RFDS-002 generic Disconnect against the secondary alias only (emulator,
    ...    not UDP — see KW-009's Documentation for why).
    Open N83624 Emulator    ${SECONDARY_ALIAS}
    Switch N83624 Connection    ${SECONDARY_ALIAS}
    Disconnect    ${SECONDARY_ALIAS}
    ${connections}=    List N83624 Connections
    List Should Not Contain Value    ${connections}    ${SECONDARY_ALIAS}
    Switch N83624 Connection    ${ALIAS}

KW-014 Is Connected
    ${connected}=    Is Connected    ${ALIAS}
    Should Be Equal    ${connected}    ${TRUE}
    ${unknown}=    Is Connected    does-not-exist
    Should Be Equal    ${unknown}    ${FALSE}

KW-015 Get Connection State
    ${state}=    Get Connection State    alias=${ALIAS}    refresh=${TRUE}
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Log Dictionary    ${state}

KW-016 Check Communication
    ${ok}=    Check Communication    ${ALIAS}
    Should Be Equal    ${ok}    ${TRUE}

KW-017 Get Identity
    ${identity}=    Get Identity    alias=${ALIAS}
    Should Not Be Empty    ${identity}

# ----------------------------------------------------------------------
# Safety limits and output arming
# ----------------------------------------------------------------------
KW-018 Set Channel Safety Limits
    ${limits}=    Set Channel Safety Limits    ${TEST_CHANNEL}    ${MAX_VOLTAGE_V}    ${MAX_CURRENT_MA}
    ...    alias=${ALIAS}
    Should Be Equal As Numbers    ${limits}[max_voltage_v]    ${MAX_VOLTAGE_V}

KW-019 Get Channel Safety Limits
    ${limits}=    Get Channel Safety Limits    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${limits}[max_voltage_v] > 0

KW-020 Arm Channel Output
    Skip If    not ${ALLOW_OUTPUT_ON}    Set ALLOW_OUTPUT_ON:true to exercise output arming.
    Arm Channel Output    ${TEST_CHANNEL}    ENABLE OUTPUT    alias=${ALIAS}
    Channel Output Should Be Armed    ${TEST_CHANNEL}    alias=${ALIAS}
    Disarm Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}

KW-021 Disarm Channel Output
    Set Channel Safety Limits    ${TEST_CHANNEL}    ${MAX_VOLTAGE_V}    ${MAX_CURRENT_MA}    alias=${ALIAS}
    Arm Channel Output    ${TEST_CHANNEL}    ENABLE OUTPUT    alias=${ALIAS}
    Disarm Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}
    Run Keyword And Expect Error    *not armed*    Channel Output Should Be Armed    ${TEST_CHANNEL}
    ...    alias=${ALIAS}

KW-022 Disarm All Channel Outputs
    Set Channel Safety Limits    ${TEST_CHANNEL}    ${MAX_VOLTAGE_V}    ${MAX_CURRENT_MA}    alias=${ALIAS}
    Arm Channel Output    ${TEST_CHANNEL}    ENABLE OUTPUT    alias=${ALIAS}
    Disarm All Channel Outputs    alias=${ALIAS}
    Run Keyword And Expect Error    *not armed*    Channel Output Should Be Armed    ${TEST_CHANNEL}
    ...    alias=${ALIAS}

KW-023 Channel Output Should Be Armed
    Set Channel Safety Limits    ${TEST_CHANNEL}    ${MAX_VOLTAGE_V}    ${MAX_CURRENT_MA}    alias=${ALIAS}
    Arm Channel Output    ${TEST_CHANNEL}    ENABLE OUTPUT    alias=${ALIAS}
    Channel Output Should Be Armed    ${TEST_CHANNEL}    alias=${ALIAS}
    Disarm Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}

# ----------------------------------------------------------------------
# Mode and configuration (output stays off unless ALLOW_OUTPUT_ON)
# ----------------------------------------------------------------------
KW-024 Set Channel Mode
    ${mode}=    Set Channel Mode    ${TEST_CHANNEL}    SOURCE    alias=${ALIAS}
    Should Be Equal    ${mode}    SOURCE

KW-025 Get Channel Mode
    ${mode}=    Get Channel Mode    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Not Be Empty    ${mode}

KW-026 Configure Source Mode
    Configure Source Mode    ${TEST_CHANNEL}    ${SAFE_TEST_VOLTAGE}    ${SAFE_TEST_CURRENT_MA}
    ...    current_range=AUTO    output=${FALSE}    alias=${ALIAS}
    ${mode}=    Get Channel Mode    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${mode}    SOURCE

KW-027 Configure Charge Mode
    Configure Charge Mode    ${TEST_CHANNEL}    ${SAFE_TEST_VOLTAGE}    ${SAFE_TEST_CURRENT_MA}    ${100}
    ...    output=${FALSE}    alias=${ALIAS}
    ${mode}=    Get Channel Mode    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${mode}    CHARGE

KW-028 Configure SOC Profile
    ${steps}=    Create List
    ...    ${{ {"capacity_mah": 10, "voltage_v": ${SAFE_TEST_VOLTAGE}, "current_limit_ma": ${SAFE_TEST_CURRENT_MA}, "resistance_mohm": 1} }}
    Configure SOC Profile    ${TEST_CHANNEL}    ${steps}    output=${FALSE}    alias=${ALIAS}
    ${mode}=    Get Channel Mode    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${mode}    SOC

KW-029 Configure Sequence Profile
    ${steps}=    Create List
    ...    ${{ {"voltage_v": ${SAFE_TEST_VOLTAGE}, "current_limit_ma": ${SAFE_TEST_CURRENT_MA}, "resistance_mohm": 1, "runtime_s": 1.0} }}
    Configure Sequence Profile    ${TEST_CHANNEL}    ${1}    ${steps}    output=${FALSE}    alias=${ALIAS}
    ${mode}=    Get Channel Mode    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${mode}    SEQUENCE

# ----------------------------------------------------------------------
# Output control
# ----------------------------------------------------------------------
KW-030 Enable Channel Output
    Skip If    not ${ALLOW_OUTPUT_ON}    Set ALLOW_OUTPUT_ON:true to exercise output enable.
    Configure Source Mode    ${TEST_CHANNEL}    ${SAFE_TEST_VOLTAGE}    ${SAFE_TEST_CURRENT_MA}    output=${FALSE}
    ...    alias=${ALIAS}
    Arm Channel Output    ${TEST_CHANNEL}    ENABLE OUTPUT    alias=${ALIAS}
    Enable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}
    Channel Output Should Be On    ${TEST_CHANNEL}    alias=${ALIAS}
    Disable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}

KW-031 Disable Channel Output
    Disable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}
    Channel Output Should Be Off    ${TEST_CHANNEL}    alias=${ALIAS}

KW-032 All N83624 Outputs Off
    All N83624 Outputs Off    alias=${ALIAS}
    Channel Output Should Be Off    ${TEST_CHANNEL}    alias=${ALIAS}

KW-033 Get Channel Output State
    ${state}=    Get Channel Output State    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${state}    ${FALSE}

KW-034 Channel Output Should Be On
    Skip If    not ${ALLOW_OUTPUT_ON}    Set ALLOW_OUTPUT_ON:true to exercise output enable.
    Configure Source Mode    ${TEST_CHANNEL}    ${SAFE_TEST_VOLTAGE}    ${SAFE_TEST_CURRENT_MA}    output=${FALSE}
    ...    alias=${ALIAS}
    Arm Channel Output    ${TEST_CHANNEL}    ENABLE OUTPUT    alias=${ALIAS}
    Enable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}
    Channel Output Should Be On    ${TEST_CHANNEL}    alias=${ALIAS}
    Disable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}

KW-035 Channel Output Should Be Off
    Disable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}
    Channel Output Should Be Off    ${TEST_CHANNEL}    alias=${ALIAS}

# ----------------------------------------------------------------------
# Measurements
# ----------------------------------------------------------------------
KW-036 Measure Channel Voltage
    ${voltage}=    Measure Channel Voltage    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${voltage} >= 0

KW-037 Measure Channel Current
    ${current}=    Measure Channel Current    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${current} >= 0

KW-038 Measure Channel Power
    ${power}=    Measure Channel Power    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${power} >= 0

KW-039 Measure Channel Resistance
    ${resistance}=    Measure Channel Resistance    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${resistance} >= 0

KW-040 Measure Channel Capacity
    ${capacity}=    Measure Channel Capacity    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be True    ${capacity} >= 0

KW-041 Measure Channel
    ${values}=    Measure Channel    ${TEST_CHANNEL}    alias=${ALIAS}
    Dictionary Should Contain Key    ${values}    voltage_v
    Dictionary Should Contain Key    ${values}    current_ma
    Log Dictionary    ${values}

KW-042 Measure Voltage Channels
    [Documentation]    ``channels`` must be a Robot list or CSV string, not a bare integer —
    ...    confirmed by running this suite: passing TEST_CHANNEL directly raised
    ...    ValidationError("channels must be a list or CSV string; got int").
    ${channels}=    Create List    ${TEST_CHANNEL}
    ${values}=    Measure Voltage Channels    ${channels}    alias=${ALIAS}
    Dictionary Should Contain Key    ${values}    ${TEST_CHANNEL}

KW-043 Channel Voltage Should Be Within
    ${voltage}=    Measure Channel Voltage    ${TEST_CHANNEL}    alias=${ALIAS}
    Channel Voltage Should Be Within    ${TEST_CHANNEL}    ${voltage}    ${0.5}    alias=${ALIAS}

KW-044 Channel Current Should Be Within
    ${current}=    Measure Channel Current    ${TEST_CHANNEL}    alias=${ALIAS}
    Channel Current Should Be Within    ${TEST_CHANNEL}    ${current}    ${50}    alias=${ALIAS}

KW-045 Wait Until Channel Voltage Is Within
    ${voltage}=    Measure Channel Voltage    ${TEST_CHANNEL}    alias=${ALIAS}
    Wait Until Channel Voltage Is Within    ${TEST_CHANNEL}    ${voltage}    ${0.5}    timeout=${2}
    ...    alias=${ALIAS}

KW-046 Wait Until Channel Current Is Within
    ${current}=    Measure Channel Current    ${TEST_CHANNEL}    alias=${ALIAS}
    Wait Until Channel Current Is Within    ${TEST_CHANNEL}    ${current}    ${50}    timeout=${2}
    ...    alias=${ALIAS}

KW-047 Get Channel Status
    ${status}=    Get Channel Status    ${TEST_CHANNEL}    alias=${ALIAS}
    Log Dictionary    ${status}

KW-048 Get Channel Event
    ${event}=    Get Channel Event    ${TEST_CHANNEL}    alias=${ALIAS}
    Log Dictionary    ${event}

KW-049 Get Channel Configuration
    ${config}=    Get Channel Configuration    ${TEST_CHANNEL}    alias=${ALIAS}
    Log Dictionary    ${config}

# ----------------------------------------------------------------------
# Protection and capture rate
# ----------------------------------------------------------------------
KW-050 Set Channel Protection Limits
    Set Channel Protection Limits    ${TEST_CHANNEL}    ${MAX_CURRENT_MA}    ${MAX_VOLTAGE_V}    ${1000}
    ...    alias=${ALIAS}

KW-051 Set Channel Capture Rate
    ${original}=    Get Channel Capture Rate    ${TEST_CHANNEL}    alias=${ALIAS}
    ${test}=    Set Variable If    '${original}' == 'MEDIUM_120MS'    SLOW_480MS    MEDIUM_120MS
    ${applied}=    Set Channel Capture Rate    ${TEST_CHANNEL}    ${test}    alias=${ALIAS}
    Should Be Equal    ${applied}    ${test}
    Set Channel Capture Rate    ${TEST_CHANNEL}    ${original}    alias=${ALIAS}

KW-052 Get Channel Capture Rate
    ${rate}=    Get Channel Capture Rate    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Not Be Empty    ${rate}

# ----------------------------------------------------------------------
# Heartbeat and recovery
# ----------------------------------------------------------------------
KW-053 Start N83624 Heartbeat
    Start N83624 Heartbeat    interval_s=${1}    fail_after=${3}    alias=${ALIAS}
    Sleep    ${0.2}
    Stop N83624 Heartbeat    alias=${ALIAS}

KW-054 Stop N83624 Heartbeat
    Start N83624 Heartbeat    interval_s=${1}    alias=${ALIAS}
    Stop N83624 Heartbeat    alias=${ALIAS}

KW-055 Get N83624 Communication Health
    ${health}=    Get N83624 Communication Health    alias=${ALIAS}
    Should Be Equal    ${health}[state]    ready
    Log Dictionary    ${health}

KW-056 Recover N83624 Connection
    [Documentation]    Forces a reconnect cycle (transport close/reopen + identity resync) —
    ...    safe on its own, but momentarily drops the TCP session, so this runs last among
    ...    the connection-affecting tests.
    Recover N83624 Connection    alias=${ALIAS}
    ${connected}=    Is Connected    ${ALIAS}
    Should Be Equal    ${connected}    ${TRUE}

# ----------------------------------------------------------------------
# Raw SCPI escape hatch
# ----------------------------------------------------------------------
KW-057 Enable Raw SCPI
    Enable Raw SCPI    ENABLE RAW SCPI    alias=${ALIAS}

KW-058 Raw SCPI Query
    [Documentation]    *IDN? is a universal, non-mutating SCPI query.
    ${response}=    Raw SCPI Query    *IDN?    alias=${ALIAS}
    Should Not Be Empty    ${response}

KW-059 Raw SCPI Write
    [Documentation]    Writes OUTPut<channel>:ONOFF 0 directly — a genuine write-only SCPI
    ...    command, unlike a query such as *OPC?. Confirmed by running this suite: sending a
    ...    query via Raw SCPI Write still gets a response from the device, which is never
    ...    read (Raw SCPI Write doesn't read a reply) and desyncs the *next* query on that
    ...    same connection, which receives the stale reply instead of its own. Verifies via
    ...    the typed Get Channel Output State keyword afterward.
    Raw SCPI Write    OUTPut${TEST_CHANNEL}:ONOFF 0    alias=${ALIAS}
    ${state}=    Get Channel Output State    ${TEST_CHANNEL}    alias=${ALIAS}
    Should Be Equal    ${state}    ${FALSE}

# ----------------------------------------------------------------------
# Emulator-only keywords (approved-simulator allowance, see suite Documentation)
# ----------------------------------------------------------------------
KW-060 Set Emulator Channel Measurement
    Set Emulator Channel Measurement    ${TEST_CHANNEL}    voltage_v=${3.7}    current_ma=${100}
    ...    alias=${EMULATOR_ALIAS}
    ${values}=    Measure Channel    ${TEST_CHANNEL}    alias=${EMULATOR_ALIAS}
    Should Be Equal As Numbers    ${values}[voltage_v]    ${3.7}
    Run Keyword And Expect Error    *not an emulator*
    ...    Set Emulator Channel Measurement    ${TEST_CHANNEL}    voltage_v=${1}    alias=${ALIAS}

KW-061 Get Emulator Command Log
    ${log}=    Get Emulator Command Log    alias=${EMULATOR_ALIAS}
    Should Not Be Empty    ${log}
    Run Keyword And Expect Error    *not an emulator*
    ...    Get Emulator Command Log    alias=${ALIAS}

# ----------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------
KW-062 Export Diagnostic Bundle
    ${path}=    Export Diagnostic Bundle    alias=${ALIAS}
    Should Not Be Empty    ${path}
    File Should Exist    ${path}
    Log    Diagnostic bundle written to ${path}

*** Keywords ***
Initialize Hardware Conformance
    [Documentation]    Deliberately does NOT open EMULATOR_ALIAS here — KW-005 (Open N83624
    ...    Emulator) is what creates it, per its own Documentation and this suite's fixed,
    ...    sequential (non-randomized) test order; opening it twice under the same alias
    ...    would collide with KW-005 itself (SessionStateError: alias already exists).
    Capture Software Evidence
    Open N83624 TCP Connection    ${ALIAS}    host=${HOST}    port=${PORT}    timeout=${TIMEOUT}
    ...    max_voltage_v=${MAX_VOLTAGE_V}    max_current_ma=${MAX_CURRENT_MA}
    All N83624 Outputs Off    alias=${ALIAS}

Capture Software Evidence
    ${source_version}=    Evaluate    rf_ngi_n83624.RELEASE_VERSION    modules=rf_ngi_n83624
    ${distribution_version}=    Evaluate
    ...    importlib.metadata.version("rf-ngi-n83624")    modules=importlib.metadata
    ${robot_version}=    Evaluate    robot.__version__    modules=robot
    ${python_version}=    Evaluate    platform.python_version()    modules=platform
    Set Suite Metadata    Driver source version    ${source_version}
    Set Suite Metadata    Installed distribution version    ${distribution_version}
    Set Suite Metadata    Robot Framework version    ${robot_version}
    Set Suite Metadata    Python version    ${python_version}
    Log To Console    Driver source=${source_version}; Robot=${robot_version}; Python=${python_version}
    Should Be Equal    ${source_version}    ${EXPECTED_RELEASE_VERSION}
    ...    Source package version ${source_version} does not match suite release ${EXPECTED_RELEASE_VERSION}.

Prepare Bench For Keyword Test
    [Documentation]    Only resets TEST_CHANNEL, not a full 24-channel All N83624 Outputs Off
    ...    sweep — every test case in this suite only ever touches TEST_CHANNEL, and at 24
    ...    channels x 2 SCPI round-trips (write + readback) each, a full sweep before and
    ...    after all 62 test cases adds thousands of avoidable round-trips. The full sweep
    ...    still runs once at Suite Setup and once at Suite Teardown.
    ${connections}=    List N83624 Connections
    IF    "${ALIAS}" not in ${connections}
        Open N83624 TCP Connection    ${ALIAS}    host=${HOST}    port=${PORT}    timeout=${TIMEOUT}
        ...    max_voltage_v=${MAX_VOLTAGE_V}    max_current_ma=${MAX_CURRENT_MA}
    END
    Switch N83624 Connection    ${ALIAS}
    Run Keyword And Ignore Error    Disarm All Channel Outputs    alias=${ALIAS}
    Run Keyword And Ignore Error    Disable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}

Per Test Safe Teardown
    Run Keyword And Ignore Error    Disarm All Channel Outputs    alias=${ALIAS}
    Run Keyword And Ignore Error    Disable Channel Output    ${TEST_CHANNEL}    alias=${ALIAS}

Final Safe Teardown
    Run Keyword And Ignore Error    Disarm All Channel Outputs    alias=${ALIAS}
    Run Keyword And Ignore Error    All N83624 Outputs Off    alias=${ALIAS}
    Run Keyword And Ignore Error    Close All N83624 Connections
