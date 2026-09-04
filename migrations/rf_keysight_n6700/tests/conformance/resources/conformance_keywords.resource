*** Settings ***
Library    OperatingSystem
Library    Collections
Library    String
Library    DateTime

*** Keywords ***
Connect Self Check Instrument
    IF    $CONNECTION_TYPE == "simulated"
        Connect To N6700
        ...    alias=${N6700_ALIAS}
        ...    connection_type=simulated
        ...    audit_log_path=${PROTOCOL_TRACE}
    ELSE
        Skip If    not $HIL_ENABLE    Set HIL_ENABLE:true to run against physical hardware.
        Should Not Be Equal    ${N6700_RESOURCE}    NOT_SET
        ...    msg=Supply N6700_RESOURCE as a VISA resource or Ethernet host.
        IF    $CONNECTION_TYPE == "usb"
            Connect To N6700 Via USB
            ...    ${N6700_RESOURCE}
            ...    ${N6700_ALIAS}
            ...    discover=${TRUE}
            ...    reset_on_connect=${FALSE}
            ...    clear_errors_on_connect=${TRUE}
            ...    audit_log_path=${PROTOCOL_TRACE}
        ELSE
            Connect To N6700
            ...    ${N6700_RESOURCE}
            ...    ${N6700_ALIAS}
            ...    ${CONNECTION_TYPE}
            ...    ${N6700_PORT}
            ...    discover=${TRUE}
            ...    reset_on_connect=${FALSE}
            ...    clear_errors_on_connect=${TRUE}
            ...    audit_log_path=${PROTOCOL_TRACE}
        END
    END

Prepare N6775A Self Check
    Normalize Runtime Boolean Variables
    Validate Safety Variables
    Remove File    ${PROTOCOL_TRACE}
    Connect Self Check Instrument
    Clear N6700 Status
    ${startup_errors}=    Drain N6700 Errors
    Length Should Be    ${startup_errors}    0
    Capture Environment Evidence
    Validate Connected Mainframe And Module
    Capture Original Channel State
    Turn Off N6700 Output    ${CHANNEL}
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}
    Clear N6700 Status
    ${errors}=    Drain N6700 Errors
    Length Should Be    ${errors}    0

Normalize Runtime Boolean Variables
    ${channel_number}=         Convert To Integer    ${CHANNEL}
    ${channel_key}=            Convert To String     ${channel_number}
    ${hil_enable}=             Convert To Boolean    ${HIL_ENABLE}
    ${allow_reset}=            Convert To Boolean    ${ALLOW_RESET}
    ${allow_active_output}=    Convert To Boolean    ${ALLOW_ACTIVE_OUTPUT}
    Set Suite Variable    ${CHANNEL}                ${channel_number}
    Set Suite Variable    ${CHANNEL_KEY}            ${channel_key}
    Set Suite Variable    ${HIL_ENABLE}             ${hil_enable}
    Set Suite Variable    ${ALLOW_RESET}            ${allow_reset}
    Set Suite Variable    ${ALLOW_ACTIVE_OUTPUT}    ${allow_active_output}

Validate Safety Variables
    ${voltage_ok}=    Evaluate    0.0 <= float($TEST_VOLTAGE) <= float($MODULE_MAX_VOLTAGE)
    ${current_ok}=    Evaluate    0.0 < float($TEST_CURRENT_LIMIT) <= float($MODULE_MAX_CURRENT)
    ${power_ok}=      Evaluate    float($TEST_VOLTAGE) * float($TEST_CURRENT_LIMIT) <= float($MODULE_MAX_POWER)
    ${ovp_ok}=        Evaluate    float($TEST_VOLTAGE) < float($TEST_OVP) <= float($MODULE_MAX_VOLTAGE)
    Should Be True    ${voltage_ok}    Unsafe TEST_VOLTAGE for N6775A.
    Should Be True    ${current_ok}    Unsafe TEST_CURRENT_LIMIT for N6775A.
    Should Be True    ${power_ok}      Requested V*I exceeds the N6775A power rating.
    Should Be True    ${ovp_ok}        TEST_OVP must be above TEST_VOLTAGE and within module rating.

Capture Environment Evidence
    ${python}=    Evaluate    sys.version    modules=sys
    ${robot}=     Evaluate    robot.__version__    modules=robot
    ${platform}=  Evaluate    platform.platform()    modules=platform
    ${data}=      Create Dictionary
    ...    python=${python}
    ...    robot_framework=${robot}
    ...    platform=${platform}
    ...    connection_type=${CONNECTION_TYPE}
    ...    resource=${N6700_RESOURCE}
    ...    channel=${CHANNEL}
    ...    expected_module=${EXPECTED_MODULE}
    ...    allow_reset=${ALLOW_RESET}
    ...    allow_active_output=${ALLOW_ACTIVE_OUTPUT}
    ${json}=    Evaluate    json.dumps($data, indent=2, sort_keys=True)    modules=json
    Create File    ${ENVIRONMENT_EVIDENCE}    ${json}${\n}

Validate Connected Mainframe And Module
    ${identity}=    Get N6700 Identity
    Dictionary Should Contain Key    ${identity}    manufacturer
    Dictionary Should Contain Key    ${identity}    model
    Dictionary Should Contain Key    ${identity}    serial
    Dictionary Should Contain Key    ${identity}    firmware
    Should Match Regexp    ${identity}[manufacturer]    (?i).*(KEYSIGHT|AGILENT|HEWLETT-PACKARD).*
    ${count}=    Get N6700 Channel Count
    Should Be True    1 <= ${CHANNEL} <= ${count}
    ${info}=    Get N6700 Channel Information    ${CHANNEL}
    Should Be Equal As Strings    ${info}[model]    ${EXPECTED_MODULE}    ignore_case=${TRUE}
    Should Be Equal As Strings    ${info}[capabilities][module_type]    power_supply
    Should Be True    ${info}[capabilities][supports_voltage_source]
    ${device}=    Create Dictionary
    ...    identity=${identity}
    ...    channel_count=${count}
    ...    selected_channel=${CHANNEL}
    ...    channel_information=${info}
    ${json}=    Evaluate    json.dumps($device, indent=2, sort_keys=True)    modules=json
    Create File    ${DEVICE_EVIDENCE}    ${json}${\n}
    Set Suite Variable    ${IDENTITY}    ${identity}
    Set Suite Variable    ${CHANNEL_INFO}    ${info}

Capture Original Channel State
    ${output}=     Get N6700 Output State    ${CHANNEL}
    ${voltage}=    Get N6700 Voltage Setpoint    ${CHANNEL}
    ${current}=    Get N6700 Current Limit    ${CHANNEL}
    ${ovp}=        Get N6700 Over Voltage Protection    ${CHANNEL}
    ${ocp}=        Get N6700 Over Current Protection    ${CHANNEL}
    Set Suite Variable    ${ORIGINAL_OUTPUT}     ${output}
    Set Suite Variable    ${ORIGINAL_VOLTAGE}    ${voltage}
    Set Suite Variable    ${ORIGINAL_CURRENT}    ${current}
    Set Suite Variable    ${ORIGINAL_OVP}        ${ovp}
    Set Suite Variable    ${ORIGINAL_OCP}        ${ocp}
    Log    Original output state was ${output}; teardown intentionally leaves the output OFF.

Keep Tested Channel Safe
    Run Keyword And Ignore Error    Turn Off N6700 Output    ${CHANNEL}

Restore Safe Channel State And Disconnect
    Run Keyword And Ignore Error    Shutdown All N6700 Channels
    Run Keyword And Ignore Error    Turn Off N6700 Output    ${CHANNEL}
    Run Keyword And Ignore Error    Set N6700 Voltage    ${CHANNEL}    0V
    Run Keyword And Ignore Error    Set N6700 Current Limit    ${CHANNEL}    ${ORIGINAL_CURRENT}
    Run Keyword And Ignore Error    Set N6700 Over Voltage Protection    ${CHANNEL}    ${ORIGINAL_OVP}
    Run Keyword And Ignore Error    Set N6700 Over Current Protection    ${CHANNEL}    ${ORIGINAL_OCP}
    Run Keyword And Ignore Error    Set N6700 Voltage    ${CHANNEL}    ${ORIGINAL_VOLTAGE}
    Run Keyword And Ignore Error    Turn Off N6700 Output    ${CHANNEL}
    Run Keyword And Ignore Error    Disconnect All N6700

Numbers Should Be Close
    [Arguments]    ${actual}    ${expected}    ${tolerance}
    ${delta}=    Evaluate    abs(float($actual) - float($expected))
    ${ok}=       Evaluate    float($delta) <= float($tolerance)
    Should Be True    ${ok}
    ...    Actual ${actual} differs from expected ${expected} by ${delta}, tolerance ${tolerance}.

Value Should Be Finite
    [Arguments]    ${value}
    ${finite}=    Evaluate    math.isfinite(float($value))    modules=math
    Should Be True    ${finite}    Value is not finite: ${value}

Dictionary Should Contain Measurement Schema
    [Arguments]    ${measurement}
    FOR    ${key}    IN    channel    voltage_V    current_A    power_W    power_source    timestamp_iso    timestamp_unix
        Dictionary Should Contain Key    ${measurement}    ${key}
    END
    Should Be Equal As Integers    ${measurement}[channel]    ${CHANNEL}
    Should Contain Any    ${measurement}[power_source]    instrument    calculated    unavailable

Should Contain Any
    [Arguments]    ${actual}    @{allowed}
    ${ok}=    Evaluate    str($actual) in $allowed
    Should Be True    ${ok}    ${actual} was not one of ${allowed}.

Trace Should Contain
    [Arguments]    ${text}
    File Should Exist    ${PROTOCOL_TRACE}
    ${trace}=    Get File    ${PROTOCOL_TRACE}
    Should Contain    ${trace}    ${text}

Trace Should Not Contain
    [Arguments]    ${text}
    File Should Exist    ${PROTOCOL_TRACE}
    ${trace}=    Get File    ${PROTOCOL_TRACE}
    Should Not Contain    ${trace}    ${text}
