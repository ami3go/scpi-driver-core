*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Real N6700 For Output Test
Suite Teardown    Disconnect All N6700
Test Teardown     Shutdown All N6700 Channels

*** Variables ***
${N6700_RESOURCE}    NOT_SET
${ALLOW_OUTPUT_TEST}    ${FALSE}

*** Test Cases ***
Guarded Five Volt Output Test
    Configure N6700 Power Supply Channel    1    5V    100mA    output=${FALSE}    ovp=5.5V    ocp=${TRUE}
    Turn On N6700 Output    1
    Wait Until N6700 Voltage Is In Range    1    4.9V    5.1V    5s
    Turn Off N6700 Output    1

*** Keywords ***
Connect To Real N6700 For Output Test
    Skip If    '${N6700_RESOURCE}' == 'NOT_SET'    Supply --variable N6700_RESOURCE:<visa-resource>
    ${allow_output}=    Convert To Boolean    ${ALLOW_OUTPUT_TEST}
    Skip If    not $allow_output    Set ALLOW_OUTPUT_TEST to true only with a reviewed fixture
    Connect To N6700 Via VISA    ${N6700_RESOURCE}    hardware
