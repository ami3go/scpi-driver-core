*** Settings ***
Documentation    RFDS-019 real-device self-check for a Keysight N6775A module. Non-energizing by default.
Library          rf_keysight_n6700.KeysightN6700Library    auto_shutdown=${TRUE}    strict_errors=${TRUE}
Resource         resources/conformance_variables.resource
Resource         resources/conformance_keywords.resource
Suite Setup      Prepare N6775A Self Check
Suite Teardown   Restore Safe Channel State And Disconnect
Test Teardown    Keep Tested Channel Safe

*** Test Cases ***
01 Session Selection And Alias API Respond Correctly
    ${current}=    Get Current N6700 Alias
    Should Be Equal    ${current}    ${N6700_ALIAS}
    ${aliases}=    Get Connected N6700 Aliases
    List Should Contain Value    ${aliases}    ${N6700_ALIAS}
    ${selected}=    Select N6700    ${N6700_ALIAS}
    Should Be Equal    ${selected}    ${N6700_ALIAS}

02 Identity And N6775A Discovery Responses Are Valid
    ${identity}=    Get N6700 Identity
    Should Be Equal    ${identity}[manufacturer]    ${IDENTITY}[manufacturer]
    Should Not Be Empty    ${identity}[model]
    Should Not Be Empty    ${identity}[serial]
    Should Not Be Empty    ${identity}[firmware]
    ${count}=    Get N6700 Channel Count
    Should Be True    ${count} >= 1
    ${modules}=    Discover N6700 Modules
    Dictionary Should Contain Key    ${modules}    ${CHANNEL_KEY}
    ${info}=    Get N6700 Channel Information    ${CHANNEL}
    Should Be Equal As Strings    ${info}[model]    ${EXPECTED_MODULE}    ignore_case=${TRUE}

03 Common SCPI Query Responses Are Valid
    ${idn}=    Query N6700 SCPI    *IDN?
    Should Contain    ${idn}    ${IDENTITY}[model]
    ${options}=    Query N6700 SCPI    *OPT?
    Should Not Be Equal    ${options}    ${NONE}
    ${opc}=    Query N6700 SCPI    *OPC?
    Should Be Equal As Integers    ${opc}    1
    ${stb}=    Query N6700 SCPI    *STB?
    ${stb_int}=    Convert To Integer    ${stb}
    Should Be True    0 <= ${stb_int} <= 255
    ${esr}=    Query N6700 SCPI    *ESR?
    ${esr_int}=    Convert To Integer    ${esr}
    Should Be True    0 <= ${esr_int} <= 255

04 Instrument Self Test Reports Pass
    Turn Off N6700 Output    ${CHANNEL}
    ${result}=    Run N6700 Self Test
    Should Be Equal As Integers    ${result}[code]    0
    Should Be True    ${result}[passed]
    Log    N6700 self-test response: ${result}

05 Status Clear Wait And Error Queue Commands Respond Correctly
    Clear N6700 Status
    Write N6700 SCPI    *WAI
    ${opc}=    Query N6700 SCPI    *OPC?
    Should Be Equal As Integers    ${opc}    1
    ${errors}=    Drain N6700 Errors
    Length Should Be    ${errors}    0
    Check N6700 Errors

06 Voltage Setpoint Command Round Trip Is Correct
    Turn Off N6700 Output    ${CHANNEL}
    ${returned}=    Set N6700 Voltage    ${CHANNEL}    ${TEST_VOLTAGE}
    Numbers Should Be Close    ${returned}    ${TEST_VOLTAGE}    ${READBACK_TOLERANCE}
    ${typed}=    Get N6700 Voltage Setpoint    ${CHANNEL}
    Numbers Should Be Close    ${typed}    ${TEST_VOLTAGE}    ${READBACK_TOLERANCE}
    ${raw}=    Query N6700 SCPI    VOLT? (@${CHANNEL})
    Numbers Should Be Close    ${raw}    ${TEST_VOLTAGE}    ${READBACK_TOLERANCE}
    Check N6700 Errors

07 Current Limit Command Round Trip Is Correct
    Turn Off N6700 Output    ${CHANNEL}
    ${returned}=    Set N6700 Current Limit    ${CHANNEL}    ${TEST_CURRENT_LIMIT}
    Numbers Should Be Close    ${returned}    ${TEST_CURRENT_LIMIT}    ${READBACK_TOLERANCE}
    ${typed}=    Get N6700 Current Limit    ${CHANNEL}
    Numbers Should Be Close    ${typed}    ${TEST_CURRENT_LIMIT}    ${READBACK_TOLERANCE}
    ${raw}=    Query N6700 SCPI    CURR? (@${CHANNEL})
    Numbers Should Be Close    ${raw}    ${TEST_CURRENT_LIMIT}    ${READBACK_TOLERANCE}
    Check N6700 Errors

08 Combined Power Supply Configuration Round Trip Is Correct
    ${result}=    Configure N6700 Power Supply Channel
    ...    ${CHANNEL}
    ...    ${TEST_VOLTAGE}
    ...    ${TEST_CURRENT_LIMIT}
    ...    output=${FALSE}
    ...    ovp=${TEST_OVP}
    ...    ocp=${TRUE}
    Should Be Equal As Integers    ${result}[channel]    ${CHANNEL}
    Should Be Equal    ${result}[output_enabled]    ${FALSE}
    Should Be Equal    ${result}[ocp_enabled]    ${TRUE}
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}
    ${voltage}=    Get N6700 Voltage Setpoint    ${CHANNEL}
    ${current}=    Get N6700 Current Limit    ${CHANNEL}
    ${ovp}=        Get N6700 Over Voltage Protection    ${CHANNEL}
    ${ocp}=        Get N6700 Over Current Protection    ${CHANNEL}
    Numbers Should Be Close    ${voltage}    ${TEST_VOLTAGE}          ${READBACK_TOLERANCE}
    Numbers Should Be Close    ${current}    ${TEST_CURRENT_LIMIT}    ${READBACK_TOLERANCE}
    Numbers Should Be Close    ${ovp}        ${TEST_OVP}              ${READBACK_TOLERANCE}
    Should Be True    ${ocp}
    Check N6700 Errors

09 Output Off Command Family And Readback Are Correct
    ${state}=    Set N6700 Output    ${CHANNEL}    ${FALSE}
    Should Be Equal    ${state}    ${FALSE}
    Turn Off N6700 Output    ${CHANNEL}
    ${actual}=    Get N6700 Output State    ${CHANNEL}
    Should Be Equal    ${actual}    ${FALSE}
    ${channels}=    Set N6700 Outputs    ${CHANNEL}    ${FALSE}
    List Should Contain Value    ${channels}    ${CHANNEL}
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}
    Check N6700 Errors

10 OVP And OCP Commands Round Trip Correctly
    Turn Off N6700 Output    ${CHANNEL}
    ${ovp_set}=    Set N6700 Over Voltage Protection    ${CHANNEL}    ${TEST_OVP}
    ${ovp_get}=    Get N6700 Over Voltage Protection    ${CHANNEL}
    Numbers Should Be Close    ${ovp_set}    ${TEST_OVP}    ${READBACK_TOLERANCE}
    Numbers Should Be Close    ${ovp_get}    ${TEST_OVP}    ${READBACK_TOLERANCE}
    ${ocp_on}=    Set N6700 Over Current Protection    ${CHANNEL}    ${TRUE}
    Should Be True    ${ocp_on}
    ${ocp_get}=    Get N6700 Over Current Protection    ${CHANNEL}
    Should Be True    ${ocp_get}
    ${ocp_off}=    Set N6700 Over Current Protection    ${CHANNEL}    ${FALSE}
    Should Be Equal    ${ocp_off}    ${FALSE}
    ${ocp_get}=    Get N6700 Over Current Protection    ${CHANNEL}
    Should Be Equal    ${ocp_get}    ${FALSE}
    ${raw_ocp}=    Query N6700 SCPI    CURR:PROT:STAT? (@${CHANNEL})
    Should Be Equal As Integers    ${raw_ocp}    0
    Check N6700 Errors

11 Measurement Commands Return Valid Schemas
    Turn Off N6700 Output    ${CHANNEL}
    ${voltage}=    Measure N6700 Voltage    ${CHANNEL}
    ${current}=    Measure N6700 Current    ${CHANNEL}
    ${power}=      Measure N6700 Power      ${CHANNEL}
    ${channel_measurement}=    Measure N6700 Channel    ${CHANNEL}
    ${all_measurements}=        Measure All N6700 Channels
    Value Should Be Finite    ${voltage}
    Value Should Be Finite    ${current}
    Dictionary Should Contain Key    ${power}    power_W
    Dictionary Should Contain Key    ${power}    power_source
    Dictionary Should Contain Measurement Schema    ${channel_measurement}
    Dictionary Should Contain Key    ${all_measurements}    ${CHANNEL_KEY}
    Trace Should Not Contain    "command": "MEAS:POW? (@${CHANNEL})"
    Check N6700 Errors

12 Measurement Assertion And Polling Keywords Confirm Responses
    Turn Off N6700 Output    ${CHANNEL}
    ${voltage}=    Measure N6700 Voltage    ${CHANNEL}
    ${current}=    Measure N6700 Current    ${CHANNEL}
    ${power_data}=    Measure N6700 Power    ${CHANNEL}
    ${voltage_checked}=    N6700 Voltage Should Be
    ...    ${CHANNEL}    ${voltage}    ${MEASUREMENT_TOLERANCE}
    ${current_checked}=    N6700 Current Should Be
    ...    ${CHANNEL}    ${current}    ${MEASUREMENT_TOLERANCE}
    Value Should Be Finite    ${voltage_checked}
    Value Should Be Finite    ${current_checked}
    IF    $power_data["power_W"] is not None
        ${power_checked}=    N6700 Power Should Be
        ...    ${CHANNEL}    ${power_data}[power_W]    ${MEASUREMENT_TOLERANCE}
        Value Should Be Finite    ${power_checked}
    END
    ${low}=     Evaluate    float($voltage) - float($MEASUREMENT_TOLERANCE)
    ${high}=    Evaluate    float($voltage) + float($MEASUREMENT_TOLERANCE)
    ${waited}=    Wait Until N6700 Voltage Is In Range
    ...    ${CHANNEL}    ${low}    ${high}    timeout=2s    poll_interval=100ms
    Value Should Be Finite    ${waited}

13 Protection Status And Safe Clear Responses Are Valid
    Turn Off N6700 Output    ${CHANNEL}
    ${before}=    Get N6700 Protection Status    ${CHANNEL}
    Dictionary Should Contain Key    ${before}    channel
    Dictionary Should Contain Key    ${before}    active
    Dictionary Should Contain Key    ${before}    raw_status
    ${raw_status}=    Query N6700 SCPI    STAT:QUES:COND? (@${CHANNEL})
    Should Be Equal As Integers    ${before}[raw_status]    ${raw_status}
    ${result}=    Clear N6700 Protection
    ...    ${CHANNEL}
    ...    restore_output=${FALSE}
    ...    force_output_off_first=${TRUE}
    ...    verify_cleared=${TRUE}
    Dictionary Should Contain Key    ${result}    protection_before
    Dictionary Should Contain Key    ${result}    protection_after
    Should Be Equal    ${result}[output_state_after]    ${FALSE}
    Length Should Be    ${result}[errors]    0
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}
    Check N6700 Errors

14 Invalid SCPI Produces Error And Communication Recovers
    Clear N6700 Status
    Write N6700 SCPI    N6775A:INVALID:COMMAND    check_errors=${FALSE}
    ${errors}=    Drain N6700 Errors
    Should Not Be Empty    ${errors}
    Should Not Be Equal As Integers    ${errors}[0][code]    0
    Should Not Be Empty    ${errors}[0][message]
    ${idn}=    Query N6700 SCPI    *IDN?
    Should Contain    ${idn}    ${IDENTITY}[model]
    Check N6700 Errors

15 Invalid Arguments Are Rejected Before Transmission
    Run Keyword And Expect Error    *channel must be between 1 and 4*
    ...    Set N6700 Voltage    0    1V
    Run Keyword And Expect Error    *must be numeric*
    ...    Set N6700 Voltage    ${CHANNEL}    invalid-voltage
    Run Keyword And Expect Error    *minimum cannot be greater than maximum*
    ...    Wait Until N6700 Voltage Is In Range    ${CHANNEL}    2V    1V
    Run Keyword And Expect Error    *must be a boolean value*
    ...    Set N6700 Output    ${CHANNEL}    maybe
    ${errors}=    Drain N6700 Errors
    Length Should Be    ${errors}    0

16 N6775A Rejects SMU And Electronic Load Keywords Correctly
    Run Keyword And Expect Error    *not an SMU*    Set N6700 SMU Mode    ${CHANNEL}    voltage
    Run Keyword And Expect Error    *not an SMU*    Get N6700 SMU Mode    ${CHANNEL}
    Run Keyword And Expect Error    *not an SMU*
    ...    Configure N6700 SMU Voltage Priority    ${CHANNEL}    1V    100mA
    Run Keyword And Expect Error    *not an SMU*
    ...    Configure N6700 SMU Current Priority    ${CHANNEL}    100mA    1V
    Run Keyword And Expect Error    *not an SMU*
    ...    Set N6700 SMU Output Off Mode    ${CHANNEL}    high_z
    Run Keyword And Expect Error    *not an SMU*
    ...    Get N6700 SMU Output Off Mode    ${CHANNEL}
    Run Keyword And Expect Error    *not an electronic load*    Set N6700 Load Mode    ${CHANNEL}    cc
    Run Keyword And Expect Error    *not an electronic load*    Get N6700 Load Mode    ${CHANNEL}
    Run Keyword And Expect Error    *not an electronic load*    Set N6700 Load Level    ${CHANNEL}    100mA    cc
    Run Keyword And Expect Error    *not an electronic load*    Get N6700 Load Level    ${CHANNEL}    cc
    Run Keyword And Expect Error    *not an electronic load*    Set N6700 Load Input    ${CHANNEL}    ${FALSE}
    Run Keyword And Expect Error    *not an electronic load*    Turn On N6700 Load Input    ${CHANNEL}
    Run Keyword And Expect Error    *not an electronic load*    Turn Off N6700 Load Input    ${CHANNEL}
    Run Keyword And Expect Error    *not an electronic load*    Get N6700 Load Input State    ${CHANNEL}
    Run Keyword And Expect Error    *not an electronic load*    Configure N6700 Load CC    ${CHANNEL}    100mA
    ${errors}=    Drain N6700 Errors
    Length Should Be    ${errors}    0

17 Optional Reset Command Completes And Recovers
    [Tags]    destructive    reset
    Skip If    not $ALLOW_RESET    Set ALLOW_RESET:true to execute *RST.
    Turn Off N6700 Output    ${CHANNEL}
    Reset N6700
    ${opc}=    Query N6700 SCPI    *OPC?
    Should Be Equal As Integers    ${opc}    1
    ${info}=    Get N6700 Channel Information    ${CHANNEL}
    Should Be Equal As Strings    ${info}[model]    ${EXPECTED_MODULE}    ignore_case=${TRUE}
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}
    Check N6700 Errors

18 Optional Active Output Commands And Measurement Respond Correctly
    [Tags]    active_output    energizing
    Skip If    not $ALLOW_ACTIVE_OUTPUT
    ...    Set ALLOW_ACTIVE_OUTPUT:true only with a reviewed, unloaded or protected fixture.
    Configure N6700 Power Supply Channel
    ...    ${CHANNEL}
    ...    ${TEST_VOLTAGE}
    ...    ${TEST_CURRENT_LIMIT}
    ...    output=${FALSE}
    ...    ovp=${TEST_OVP}
    ...    ocp=${TRUE}
    ${enabled}=    Set N6700 Output    ${CHANNEL}    ${TRUE}
    Should Be True    ${enabled}
    N6700 Output Should Be    ${CHANNEL}    ${TRUE}
    ${measured}=    Wait Until N6700 Voltage Is In Range
    ...    ${CHANNEL}
    ...    ${ACTIVE_VOLTAGE_MIN}
    ...    ${ACTIVE_VOLTAGE_MAX}
    ...    timeout=${ACTIVE_TIMEOUT}
    N6700 Voltage Should Be    ${CHANNEL}    ${TEST_VOLTAGE}    ${MEASUREMENT_TOLERANCE}
    Value Should Be Finite    ${measured}
    Turn Off N6700 Output    ${CHANNEL}
    Turn On N6700 Output     ${CHANNEL}
    ${channels}=    Set N6700 Outputs    ${CHANNEL}    ${FALSE}
    List Should Contain Value    ${channels}    ${CHANNEL}
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}
    Check N6700 Errors

19 Shutdown All Channels Returns Successful Safe State
    ${result}=    Shutdown All N6700 Channels
    Should Be True    ${result}[success]
    N6700 Output Should Be    ${CHANNEL}    ${FALSE}

20 Disconnect And Reconnect Commands Recover Communication
    Disconnect N6700    ${N6700_ALIAS}
    ${aliases}=    Get Connected N6700 Aliases
    List Should Not Contain Value    ${aliases}    ${N6700_ALIAS}
    Connect Self Check Instrument
    ${idn}=    Get N6700 Identity
    Should Be Equal    ${idn}[serial]    ${IDENTITY}[serial]
    Disconnect All N6700
    ${aliases}=    Get Connected N6700 Aliases
    Length Should Be    ${aliases}    0
    Connect Self Check Instrument
    ${idn}=    Get N6700 Identity
    Should Be Equal    ${idn}[serial]    ${IDENTITY}[serial]

21 Protocol Trace Contains Required Command Families And Responses
    Trace Should Contain    "command": "*IDN?"
    Trace Should Contain    "command": "SYST:CHAN:COUN?"
    Trace Should Contain    "command": "SYST:CHAN:MOD? (@${CHANNEL})"
    Trace Should Contain    "command": "VOLT 
    Trace Should Contain    "command": "VOLT? (@${CHANNEL})"
    Trace Should Contain    "command": "CURR 
    Trace Should Contain    "command": "CURR? (@${CHANNEL})"
    Trace Should Contain    "command": "OUTP OFF,(@${CHANNEL})"
    Trace Should Contain    "command": "VOLT:PROT 
    Trace Should Contain    "command": "CURR:PROT:STAT 
    Trace Should Contain    "command": "MEAS:VOLT? (@${CHANNEL})"
    Trace Should Contain    "command": "MEAS:CURR? (@${CHANNEL})"
    Trace Should Contain    "command": "OUTP:PROT:CLE (@${CHANNEL})"
    Trace Should Contain    "command": "N6775A:INVALID:COMMAND"
    Trace Should Contain    "command": "SYST:ERR?"
    Trace Should Contain    "response":
