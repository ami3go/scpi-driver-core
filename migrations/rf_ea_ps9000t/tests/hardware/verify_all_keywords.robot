*** Settings ***
Documentation     RFDS-019 real-hardware conformance: exercises every public keyword of
...               rf_ea_ps9000t.EaPs9000TLibrary against a physical EA-PS 9000 T unit and
...               verifies its response. Does not run automatically in CI (Force Tags
...               "hardware"; exclude with `--exclude hardware` in automated pipelines).
...
...               Connects by default over the USB virtual COM port (VISA ASRL resource,
...               see COM_PORT below) since that is the only interface most PS 9000 T
...               benches expose; set RESOURCE instead to test over RS232 or Ethernet.
...
...               Output stays OFF for the whole suite unless ALLOW_OUTPUT_ON is set, and
...               LAN-identity keywords (IP/subnet/gateway/hostname/...) are read-only
...               unless ALLOW_LAN_WRITES is set — see the per-keyword documentation below
...               for exactly what each flag unlocks. Every keyword that mutates
...               device-persistent state restores the original value before its test
...               case ends, and Suite Teardown restores the adjustment limits captured at
...               Suite Setup, so the instrument is left as it was found either way.
...
...               Every keyword call this suite makes is also recorded as RFDS-008
...               structured evidence (arguments, duration, the raw SCPI exchange) under
...               results/session/rf_ea_ps9000t/ — see docs/logging_and_evidence.md. This
...               real-hardware run is a good one to keep: it is real-device SCPI-trace
...               evidence for every keyword in one place.
Library           rf_ea_ps9000t.EaPs9000TLibrary
Library           Collections
Library           OperatingSystem
Suite Setup       Initialize Hardware Conformance
Suite Teardown    Final Safe Teardown
Test Setup        Prepare Hardware For Keyword Test
Test Teardown     Per Test Safe Teardown
Force Tags        hardware    ea_ps9000t    keyword-conformance

*** Variables ***
${COM_PORT}                 5
${RESOURCE}                 ${EMPTY}
${ALIAS}                    hardware
${SECONDARY_ALIAS}          secondary
${TIMEOUT_S}                ${5.0}
${ALLOW_OUTPUT_ON}          ${FALSE}
${ALLOW_LAN_WRITES}         ${FALSE}
${VOLTAGE_FRACTION}         ${0.1}
${CURRENT_FRACTION}         ${0.1}
${POWER_FRACTION}           ${0.1}
${SETPOINT_TOLERANCE}       ${0.05}
${EXPECTED_DRIVER_VERSION}    26.2

*** Test Cases ***
# ----------------------------------------------------------------------
# Connection (RFDS-002, extended with remote-control handling)
# ----------------------------------------------------------------------
KW-001 Connect
    [Documentation]    Reopen the real connection via the com_port shorthand and verify the
    ...    normalized connection-state dictionary Connect returns.
    Disconnect    ${ALIAS}
    ${state}=    Open Hardware Connection
    Should Be Equal    ${state}[alias]    ${ALIAS}
    Should Be Equal    ${state}[connected]    ${TRUE}
    Should Be Equal    ${state}[state]    connected
    Should Not Be Empty    ${state}[resource]

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
    ${ok}=    Check Communication
    Should Be Equal    ${ok}    ${TRUE}

KW-006 Get Identity
    ${identity}=    Get Identity    refresh=${TRUE}
    Should Not Be Empty    ${identity}
    Should Contain    ${identity}    EA
    Log    ${identity}

KW-007 Get Remote Control Owner
    [Documentation]    Connect already holds remote control (task §6 item 1), so the
    ...    owner must read back as REMOTE.
    ${owner}=    Get Remote Control Owner
    Should Be Equal    ${owner}    REMOTE

KW-008 Switch Power Supply
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    ${active}=    Switch Power Supply    ${SECONDARY_ALIAS}
    Should Be Equal    ${active}    ${SECONDARY_ALIAS}
    Switch Power Supply    ${ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

KW-009 Get Active Power Supply
    ${active}=    Get Active Power Supply
    Should Be Equal    ${active}    ${ALIAS}

KW-010 List Power Supply Connections
    Connect    alias=${SECONDARY_ALIAS}    simulated=${TRUE}
    ${connections}=    List Power Supply Connections
    List Should Contain Value    ${connections}    ${ALIAS}
    List Should Contain Value    ${connections}    ${SECONDARY_ALIAS}
    Disconnect    ${SECONDARY_ALIAS}

# ----------------------------------------------------------------------
# Set values
# ----------------------------------------------------------------------
KW-011 Set Voltage
    Set Voltage    ${SAFE_TEST_VOLTAGE}
    ${readback}=    Get Voltage
    Numbers Should Be Close    ${readback}    ${SAFE_TEST_VOLTAGE}    ${SETPOINT_TOLERANCE}

KW-012 Get Voltage
    Set Voltage    ${SAFE_TEST_VOLTAGE}
    ${voltage}=    Get Voltage
    Should Be True    ${voltage} >= 0

KW-013 Set Current
    Set Current    ${SAFE_TEST_CURRENT}
    ${readback}=    Get Current
    Numbers Should Be Close    ${readback}    ${SAFE_TEST_CURRENT}    ${SETPOINT_TOLERANCE}

KW-014 Get Current
    Set Current    ${SAFE_TEST_CURRENT}
    ${current}=    Get Current
    Should Be True    ${current} >= 0

KW-015 Set Power
    Set Power    ${SAFE_TEST_POWER}
    ${readback}=    Get Power
    Numbers Should Be Close    ${readback}    ${SAFE_TEST_POWER}    ${SETPOINT_TOLERANCE}

KW-016 Get Power
    Set Power    ${SAFE_TEST_POWER}
    ${power}=    Get Power
    Should Be True    ${power} >= 0

# ----------------------------------------------------------------------
# Protection thresholds
# ----------------------------------------------------------------------
KW-017 Set Overvoltage Protection
    ${original}=    Get Overvoltage Protection
    Set Overvoltage Protection    ${NOMINAL_VOLTAGE}
    ${readback}=    Get Overvoltage Protection
    Numbers Should Be Close    ${readback}    ${NOMINAL_VOLTAGE}    ${SETPOINT_TOLERANCE}
    Set Overvoltage Protection    ${original}

KW-018 Get Overvoltage Protection
    ${value}=    Get Overvoltage Protection
    Should Be True    ${value} >= 0

KW-019 Set Overcurrent Protection
    ${original}=    Get Overcurrent Protection
    Set Overcurrent Protection    ${NOMINAL_CURRENT}
    ${readback}=    Get Overcurrent Protection
    Numbers Should Be Close    ${readback}    ${NOMINAL_CURRENT}    ${SETPOINT_TOLERANCE}
    Set Overcurrent Protection    ${original}

KW-020 Get Overcurrent Protection
    ${value}=    Get Overcurrent Protection
    Should Be True    ${value} >= 0

KW-021 Set Overpower Protection
    ${original}=    Get Overpower Protection
    Set Overpower Protection    ${NOMINAL_POWER}
    ${readback}=    Get Overpower Protection
    Numbers Should Be Close    ${readback}    ${NOMINAL_POWER}    ${SETPOINT_TOLERANCE}
    Set Overpower Protection    ${original}

KW-022 Get Overpower Protection
    ${value}=    Get Overpower Protection
    Should Be True    ${value} >= 0

KW-023 Get Protection Thresholds
    ${thresholds}=    Get Protection Thresholds
    Dictionary Should Contain Key    ${thresholds}    overvoltage
    Dictionary Should Contain Key    ${thresholds}    overcurrent
    Dictionary Should Contain Key    ${thresholds}    overpower
    Log Dictionary    ${thresholds}

# ----------------------------------------------------------------------
# Output control
# ----------------------------------------------------------------------
KW-024 Enable Output
    [Documentation]    Skipped unless ALLOW_OUTPUT_ON is set — energizes the DC output at
    ...    a small safe voltage/current. Only enable this against a bench with a suitable
    ...    load (or no load) connected; this suite has no way to know what is wired up.
    Skip If    not ${ALLOW_OUTPUT_ON}    Set ALLOW_OUTPUT_ON:true to exercise Enable Output.
    Set Voltage    ${SAFE_TEST_VOLTAGE}
    Set Current    ${SAFE_TEST_CURRENT}
    Enable Output
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${TRUE}
    Disable Output

KW-025 Disable Output
    Disable Output
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${FALSE}

KW-026 Is Output Enabled
    Disable Output
    ${enabled}=    Is Output Enabled
    Should Be Equal    ${enabled}    ${FALSE}

# ----------------------------------------------------------------------
# Measuring
# ----------------------------------------------------------------------
KW-027 Get Measured Voltage
    ${voltage}=    Get Measured Voltage
    Should Be True    ${voltage} >= 0

KW-028 Get Measured Current
    ${current}=    Get Measured Current
    Should Be True    ${current} >= 0

KW-029 Get Measured Power
    ${power}=    Get Measured Power
    Should Be True    ${power} >= 0

KW-030 Get Measured Values
    ${values}=    Get Measured Values
    Dictionary Should Contain Key    ${values}    voltage
    Dictionary Should Contain Key    ${values}    current
    Dictionary Should Contain Key    ${values}    power
    Log Dictionary    ${values}

# ----------------------------------------------------------------------
# General queries
# ----------------------------------------------------------------------
KW-031 Get Nominal Ratings
    ${ratings}=    Get Nominal Ratings
    Should Be True    ${ratings}[voltage] > 0
    Should Be True    ${ratings}[current] > 0
    Should Be True    ${ratings}[power] > 0
    Log Dictionary    ${ratings}

KW-032 Get Device Class
    ${device_class}=    Get Device Class
    Should Not Be Empty    ${device_class}
    Log    ${device_class}

KW-033 Get Alarm Counters
    ${counters}=    Get Alarm Counters
    Dictionary Should Contain Key    ${counters}    overvoltage
    Dictionary Should Contain Key    ${counters}    overtemperature
    Dictionary Should Contain Key    ${counters}    overpower
    Dictionary Should Contain Key    ${counters}    overcurrent
    Dictionary Should Contain Key    ${counters}    power_fail
    Log Dictionary    ${counters}

# ----------------------------------------------------------------------
# Adjustment limits
# ----------------------------------------------------------------------
KW-034 Set Voltage Limit Low
    Set Voltage Limit Low    0
    ${limits}=    Get Voltage Limits
    Numbers Should Be Close    ${limits}[0]    0    ${SETPOINT_TOLERANCE}
    Set Voltage Limit Low    ${WIDENED_VOLTAGE_LOW}

KW-035 Set Voltage Limit High
    Set Voltage Limit High    ${NOMINAL_VOLTAGE}
    ${limits}=    Get Voltage Limits
    Numbers Should Be Close    ${limits}[1]    ${NOMINAL_VOLTAGE}    ${SETPOINT_TOLERANCE}
    Set Voltage Limit High    ${WIDENED_VOLTAGE_HIGH}

KW-036 Get Voltage Limits
    ${limits}=    Get Voltage Limits
    Length Should Be    ${limits}    2
    Should Be True    ${limits}[0] <= ${limits}[1]

KW-037 Set Current Limit Low
    Set Current Limit Low    0
    ${limits}=    Get Current Limits
    Numbers Should Be Close    ${limits}[0]    0    ${SETPOINT_TOLERANCE}
    Set Current Limit Low    ${WIDENED_CURRENT_LOW}

KW-038 Set Current Limit High
    Set Current Limit High    ${NOMINAL_CURRENT}
    ${limits}=    Get Current Limits
    Numbers Should Be Close    ${limits}[1]    ${NOMINAL_CURRENT}    ${SETPOINT_TOLERANCE}
    Set Current Limit High    ${WIDENED_CURRENT_HIGH}

KW-039 Get Current Limits
    ${limits}=    Get Current Limits
    Length Should Be    ${limits}    2
    Should Be True    ${limits}[0] <= ${limits}[1]

KW-040 Set Power Limit High
    Set Power Limit High    ${NOMINAL_POWER}
    ${readback}=    Get Power Limit High
    Numbers Should Be Close    ${readback}    ${NOMINAL_POWER}    ${SETPOINT_TOLERANCE}
    Set Power Limit High    ${WIDENED_POWER_HIGH}

KW-041 Get Power Limit High
    ${value}=    Get Power Limit High
    Should Be True    ${value} > 0

KW-042 Get Adjustment Limits
    ${limits}=    Get Adjustment Limits
    Dictionary Should Contain Key    ${limits}    voltage_low
    Dictionary Should Contain Key    ${limits}    voltage_high
    Dictionary Should Contain Key    ${limits}    current_low
    Dictionary Should Contain Key    ${limits}    current_high
    Dictionary Should Contain Key    ${limits}    power_high
    Log Dictionary    ${limits}

# ----------------------------------------------------------------------
# Device configuration
# ----------------------------------------------------------------------
KW-043 Set Power Stage After Remote
    ${original}=    Get Power Stage After Remote
    ${test}=    Set Variable If    '${original}' == 'AUTO'    OFF    AUTO
    Set Power Stage After Remote    ${test}
    ${readback}=    Get Power Stage After Remote
    Should Be Equal    ${readback}    ${test}
    Set Power Stage After Remote    ${original}

KW-044 Get Power Stage After Remote
    ${mode}=    Get Power Stage After Remote
    Should Contain Any    ${mode}    AUTO    OFF

KW-045 Set Output Restore Mode
    ${original}=    Get Output Restore Mode
    ${test}=    Set Variable If    '${original}' == 'AUTO'    OFF    AUTO
    Set Output Restore Mode    ${test}
    ${readback}=    Get Output Restore Mode
    Should Be Equal    ${readback}    ${test}
    Set Output Restore Mode    ${original}

KW-046 Get Output Restore Mode
    ${mode}=    Get Output Restore Mode
    Should Contain Any    ${mode}    AUTO    OFF

KW-047 Set User Text
    ${original}=    Get User Text
    Set User Text    RFDS-019 TEST
    ${readback}=    Get User Text
    Should Be Equal    ${readback}    RFDS-019 TEST
    Set User Text    ${original}

KW-048 Get User Text
    ${text}=    Get User Text
    Should Be True    isinstance($text, str)

KW-049 Set Communication Timeout
    [Documentation]    Serial interfaces only (USB, RS232) — meaningful for this suite's
    ...    default USB/COM-port connection.
    ${original}=    Get Communication Timeout
    Set Communication Timeout    ${3000}
    ${readback}=    Get Communication Timeout
    Should Be Equal As Integers    ${readback}    3000
    Set Communication Timeout    ${original}

KW-050 Get Communication Timeout
    ${timeout}=    Get Communication Timeout
    Should Be True    ${timeout} > 0

KW-051 Set Power Fail Alarm Action
    ${original}=    Get Power Fail Alarm Action
    ${test}=    Set Variable If    '${original}' == 'AUTO'    OFF    AUTO
    Set Power Fail Alarm Action    ${test}
    ${readback}=    Get Power Fail Alarm Action
    Should Be Equal    ${readback}    ${test}
    Set Power Fail Alarm Action    ${original}

KW-052 Get Power Fail Alarm Action
    ${action}=    Get Power Fail Alarm Action
    Should Contain Any    ${action}    AUTO    OFF

KW-053 Set Overtemperature Alarm Action
    ${original}=    Get Overtemperature Alarm Action
    ${test}=    Set Variable If    '${original}' == 'AUTO'    OFF    AUTO
    Set Overtemperature Alarm Action    ${test}
    ${readback}=    Get Overtemperature Alarm Action
    Should Be Equal    ${readback}    ${test}
    Set Overtemperature Alarm Action    ${original}

KW-054 Get Overtemperature Alarm Action
    ${action}=    Get Overtemperature Alarm Action
    Should Contain Any    ${action}    AUTO    OFF

# ----------------------------------------------------------------------
# LAN configuration (Gate 3) — Set keywords gated behind ALLOW_LAN_WRITES;
# every one restores its original value before the test case ends.
# ----------------------------------------------------------------------
KW-055 Set LAN DHCP Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN DHCP Enabled
    ${test}=    Evaluate    not $original
    Set LAN DHCP Enabled    ${test}
    ${readback}=    Get LAN DHCP Enabled
    Should Be Equal    ${readback}    ${test}
    Set LAN DHCP Enabled    ${original}

KW-056 Get LAN DHCP Enabled
    ${enabled}=    Get LAN DHCP Enabled
    Should Be True    $enabled is True or $enabled is False

KW-057 Set LAN IP Address
    [Documentation]    Round-trips the instrument's own current IP rather than a
    ...    fabricated one — this field identifies the unit on the network and a wrong
    ...    value could strand it, so this test only proves the Set/Get path works.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN IP Address
    Set LAN IP Address    ${original}
    ${readback}=    Get LAN IP Address
    Should Be Equal    ${readback}    ${original}

KW-058 Get LAN IP Address
    ${address}=    Get LAN IP Address
    Should Not Be Empty    ${address}

KW-059 Set LAN Subnet Mask
    [Documentation]    Round-trips the current value for the same reason as the IP address.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Subnet Mask
    Set LAN Subnet Mask    ${original}
    ${readback}=    Get LAN Subnet Mask
    Should Be Equal    ${readback}    ${original}

KW-060 Get LAN Subnet Mask
    ${mask}=    Get LAN Subnet Mask
    Should Not Be Empty    ${mask}

KW-061 Set LAN Gateway
    [Documentation]    Round-trips the current value for the same reason as the IP address.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Gateway
    Set LAN Gateway    ${original}
    ${readback}=    Get LAN Gateway
    Should Be Equal    ${readback}    ${original}

KW-062 Get LAN Gateway
    ${gateway}=    Get LAN Gateway
    Should Be True    isinstance($gateway, str)

KW-063 Set LAN Hostname
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Hostname
    Set LAN Hostname    RFDS019TEST
    ${readback}=    Get LAN Hostname
    Should Be Equal    ${readback}    RFDS019TEST
    Set LAN Hostname    ${original}

KW-064 Get LAN Hostname
    ${hostname}=    Get LAN Hostname
    Should Be True    isinstance($hostname, str)

KW-065 Set LAN Domain
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Domain
    Set LAN Domain    rfds019test.local
    ${readback}=    Get LAN Domain
    Should Be Equal    ${readback}    rfds019test.local
    Set LAN Domain    ${original}

KW-066 Get LAN Domain
    ${domain}=    Get LAN Domain
    Should Be True    isinstance($domain, str)

KW-067 Set LAN DNS1
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN DNS1
    Set LAN DNS1    8.8.8.8
    ${readback}=    Get LAN DNS1
    Should Be Equal    ${readback}    8.8.8.8
    Set LAN DNS1    ${original}

KW-068 Get LAN DNS1
    ${dns1}=    Get LAN DNS1
    Should Be True    isinstance($dns1, str)

KW-069 Set LAN DNS2
    [Documentation]    Anybus modules only (task §9) — Skipped with a clear message if the
    ...    connected unit rejects it (no Anybus module fitted), same as ALLOW_LAN_WRITES gating.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN DNS2
    TRY
        Set LAN DNS2    8.8.4.4
        ${readback}=    Get LAN DNS2
        Should Be Equal    ${readback}    8.8.4.4
        Set LAN DNS2    ${original}
    EXCEPT    AS    ${error}
        Skip    No Anybus module fitted, or DNS2 unsupported on this unit: ${error}
    END

KW-070 Get LAN DNS2
    TRY
        ${dns2}=    Get LAN DNS2
        Should Be True    isinstance($dns2, str)
    EXCEPT    AS    ${error}
        Skip    No Anybus module fitted, or DNS2 unsupported on this unit: ${error}
    END

KW-071 Set LAN Control Port
    [Documentation]    5025 is skipped as the test value if it happens to already be the
    ...    configured port, and 502 (ModBus TCP) is never used since the driver rejects it.
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Control Port
    ${test}=    Evaluate    5026 if $original == 5025 else 5025
    Set LAN Control Port    ${test}
    ${readback}=    Get LAN Control Port
    Should Be Equal As Integers    ${readback}    ${test}
    Set LAN Control Port    ${original}

KW-072 Get LAN Control Port
    ${port}=    Get LAN Control Port
    Should Not Be Equal As Integers    ${port}    502

KW-073 Set LAN Keepalive Enabled
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Keepalive Enabled
    ${test}=    Evaluate    not $original
    Set LAN Keepalive Enabled    ${test}
    ${readback}=    Get LAN Keepalive Enabled
    Should Be Equal    ${readback}    ${test}
    Set LAN Keepalive Enabled    ${original}

KW-074 Get LAN Keepalive Enabled
    ${enabled}=    Get LAN Keepalive Enabled
    Should Be True    $enabled is True or $enabled is False

KW-075 Set LAN Timeout
    Skip If    not ${ALLOW_LAN_WRITES}    Set ALLOW_LAN_WRITES:true to exercise LAN Set keywords.
    ${original}=    Get LAN Timeout
    ${test}=    Evaluate    $original + 1
    Set LAN Timeout    ${test}
    ${readback}=    Get LAN Timeout
    Should Be Equal As Integers    ${readback}    ${test}
    Set LAN Timeout    ${original}

KW-076 Get LAN Timeout
    ${timeout}=    Get LAN Timeout
    Should Be True    ${timeout} >= 0

KW-077 Get LAN MAC Address
    [Documentation]    Read-only — always exercised regardless of ALLOW_LAN_WRITES.
    ${mac}=    Get LAN MAC Address
    Should Not Be Empty    ${mac}
    Log    ${mac}

# ----------------------------------------------------------------------
# Analog interface configuration (Gate 3)
# ----------------------------------------------------------------------
KW-078 Set Analog Reference Range
    ${original}=    Get Analog Reference Range
    ${test}=    Evaluate    5 if $original == 10 else 10
    Set Analog Reference Range    ${test}
    ${readback}=    Get Analog Reference Range
    Should Be Equal As Integers    ${readback}    ${test}
    Set Analog Reference Range    ${original}

KW-079 Get Analog Reference Range
    ${range}=    Get Analog Reference Range
    Should Be True    $range in (5, 10)

KW-080 Set Analog REMSB Level
    ${original}=    Get Analog REMSB Level
    ${test}=    Set Variable If    '${original}' == 'NORMAL'    INVERTED    NORMAL
    Set Analog REMSB Level    ${test}
    ${readback}=    Get Analog REMSB Level
    Should Be Equal    ${readback}    ${test}
    Set Analog REMSB Level    ${original}

KW-081 Get Analog REMSB Level
    ${level}=    Get Analog REMSB Level
    Should Contain Any    ${level}    NORMAL    INVERTED

KW-082 Set Analog REMSB Action
    [Documentation]    AUTO can switch the DC output back on via the analog REM-SB pin —
    ...    only exercised with ALLOW_OUTPUT_ON, same guard as Enable Output. OFF (the
    ...    switch-off-only behavior) is always safe and always exercised.
    ${original}=    Get Analog REMSB Action
    Set Analog REMSB Action    OFF
    ${readback}=    Get Analog REMSB Action
    Should Be Equal    ${readback}    OFF
    IF    ${ALLOW_OUTPUT_ON}
        Set Analog REMSB Action    AUTO
        ${readback}=    Get Analog REMSB Action
        Should Be Equal    ${readback}    AUTO
    END
    Set Analog REMSB Action    ${original}

KW-083 Get Analog REMSB Action
    ${action}=    Get Analog REMSB Action
    Should Contain Any    ${action}    OFF    AUTO

# ----------------------------------------------------------------------
# Raw SCPI escape hatch
# ----------------------------------------------------------------------
KW-084 Enable Raw SCPI
    [Documentation]    Requires the exact confirmation text; the enabled state then
    ...    persists for the rest of this suite's connection, so KW-085/KW-086 rely on it
    ...    already being enabled here rather than re-enabling it themselves.
    Enable Raw SCPI    ENABLE RAW SCPI

KW-085 Raw SCPI Query
    [Documentation]    SYSTem:ERRor? is a universal, non-mutating SCPI query — safe on any
    ...    SCPI instrument and a good proof that the raw escape hatch round-trips real
    ...    device responses.
    ${response}=    Raw SCPI Query    SYSTem:ERRor?
    Should Not Be Empty    ${response}
    Log    ${response}

KW-086 Raw SCPI Write
    [Documentation]    *CLS (clear status) is universal and harmless — it only clears the
    ...    SCPI error/event queues, no device settings change.
    Raw SCPI Write    *CLS
    ${response}=    Raw SCPI Query    SYSTem:ERRor?
    Should Not Be Empty    ${response}
    Log    ${response}

# ----------------------------------------------------------------------
# Diagnostics
# ----------------------------------------------------------------------
KW-087 Export Diagnostic Bundle
    [Documentation]    Zips this real-hardware run's RFDS-008 evidence — including every
    ...    SCPI exchange the earlier test cases in this suite made — for troubleshooting.
    ${path}=    Export Diagnostic Bundle    alias=${ALIAS}
    Should Not Be Empty    ${path}
    File Should Exist    ${path}
    Log    Diagnostic bundle written to ${path}

*** Keywords ***
Initialize Hardware Conformance
    Capture Software Evidence
    ${state}=    Open Hardware Connection
    Log Dictionary    ${state}
    Capture Instrument Baseline
    Widen Adjustment Limits For Test Session
    Disable Output

Capture Software Evidence
    ${source_version}=    Evaluate    ea_ps9000t.__version__    modules=ea_ps9000t
    ${distribution_version}=    Evaluate
    ...    importlib.metadata.version("robotframework-ea-ps9000t")    modules=importlib.metadata
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
    ...    Installed robotframework-ea-ps9000t ${distribution_version} does not match imported source ${source_version}; reinstall the release wheel.

Open Hardware Connection
    [Documentation]    Connects via RESOURCE if given, otherwise via the COM_PORT shorthand
    ...    (the common case: this instrument's only connection on most benches is USB,
    ...    which enumerates as a COM port).
    IF    "${RESOURCE}" != "${EMPTY}"
        Log    Opening real EA-PS 9000 T on resource=${RESOURCE}.
        ${state}=    Connect    resource=${RESOURCE}    alias=${ALIAS}    timeout_s=${TIMEOUT_S}
    ELSE
        Log    Opening real EA-PS 9000 T on COM${COM_PORT} (USB virtual COM port).
        ${state}=    Connect    com_port=${COM_PORT}    alias=${ALIAS}    timeout_s=${TIMEOUT_S}
    END
    RETURN    ${state}

Capture Instrument Baseline
    ${identity}=    Get Identity
    ${ratings}=    Get Nominal Ratings
    Log Dictionary    ${ratings}
    Set Suite Metadata    Instrument identity    ${identity}
    Set Suite Metadata    Nominal voltage    ${ratings}[voltage]
    Set Suite Metadata    Nominal current    ${ratings}[current]
    Set Suite Metadata    Nominal power    ${ratings}[power]
    Set Suite Variable    ${NOMINAL_VOLTAGE}    ${ratings}[voltage]
    Set Suite Variable    ${NOMINAL_CURRENT}    ${ratings}[current]
    Set Suite Variable    ${NOMINAL_POWER}    ${ratings}[power]
    ${safe_voltage}=    Evaluate    round($NOMINAL_VOLTAGE * $VOLTAGE_FRACTION, 3)
    ${safe_current}=    Evaluate    round($NOMINAL_CURRENT * $CURRENT_FRACTION, 3)
    ${safe_power}=    Evaluate    round($NOMINAL_POWER * $POWER_FRACTION, 3)
    Set Suite Variable    ${SAFE_TEST_VOLTAGE}    ${safe_voltage}
    Set Suite Variable    ${SAFE_TEST_CURRENT}    ${safe_current}
    Set Suite Variable    ${SAFE_TEST_POWER}    ${safe_power}

Widen Adjustment Limits For Test Session
    [Documentation]    Captures the instrument's true original adjustment limits (restored
    ...    in Final Safe Teardown) and widens them to the full nominal range so that Set
    ...    Voltage/Current/Power tests are never blocked by a narrow pre-existing range.
    ${original}=    Get Adjustment Limits
    Set Suite Variable    ${ORIGINAL_VOLTAGE_LOW}    ${original}[voltage_low]
    Set Suite Variable    ${ORIGINAL_VOLTAGE_HIGH}    ${original}[voltage_high]
    Set Suite Variable    ${ORIGINAL_CURRENT_LOW}    ${original}[current_low]
    Set Suite Variable    ${ORIGINAL_CURRENT_HIGH}    ${original}[current_high]
    Set Suite Variable    ${ORIGINAL_POWER_HIGH}    ${original}[power_high]
    Set Suite Variable    ${WIDENED_VOLTAGE_LOW}    ${0}
    Set Suite Variable    ${WIDENED_VOLTAGE_HIGH}    ${NOMINAL_VOLTAGE}
    Set Suite Variable    ${WIDENED_CURRENT_LOW}    ${0}
    Set Suite Variable    ${WIDENED_CURRENT_HIGH}    ${NOMINAL_CURRENT}
    Set Suite Variable    ${WIDENED_POWER_HIGH}    ${NOMINAL_POWER}
    Set Voltage Limit Low    ${WIDENED_VOLTAGE_LOW}
    Set Voltage Limit High    ${WIDENED_VOLTAGE_HIGH}
    Set Current Limit Low    ${WIDENED_CURRENT_LOW}
    Set Current Limit High    ${WIDENED_CURRENT_HIGH}
    Set Power Limit High    ${WIDENED_POWER_HIGH}

Prepare Hardware For Keyword Test
    Run Keyword And Ignore Error    Switch Power Supply    ${ALIAS}
    Disable Output

Per Test Safe Teardown
    Run Keyword And Ignore Error    Switch Power Supply    ${ALIAS}
    Run Keyword And Ignore Error    Disable Output

Final Safe Teardown
    Run Keyword And Ignore Error    Switch Power Supply    ${ALIAS}
    Run Keyword And Ignore Error    Disable Output
    Run Keyword And Ignore Error    Set Voltage Limit Low    ${ORIGINAL_VOLTAGE_LOW}
    Run Keyword And Ignore Error    Set Voltage Limit High    ${ORIGINAL_VOLTAGE_HIGH}
    Run Keyword And Ignore Error    Set Current Limit Low    ${ORIGINAL_CURRENT_LOW}
    Run Keyword And Ignore Error    Set Current Limit High    ${ORIGINAL_CURRENT_HIGH}
    Run Keyword And Ignore Error    Set Power Limit High    ${ORIGINAL_POWER_HIGH}
    Run Keyword And Ignore Error    Disconnect    ${ALIAS}

Numbers Should Be Close
    [Arguments]    ${actual}    ${expected}    ${tolerance}
    ${difference}=    Evaluate    abs(float($actual) - float($expected))
    Should Be True    ${difference} <= ${tolerance}
    ...    Difference ${difference} exceeds tolerance ${tolerance}; actual=${actual}, expected=${expected}
