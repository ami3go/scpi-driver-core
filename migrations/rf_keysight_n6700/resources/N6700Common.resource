*** Settings ***
Documentation    Reusable high-level keywords for N6700 test suites.

*** Keywords ***
Configure Safe DC Output
    [Arguments]    ${channel}    ${voltage}    ${current_limit}    ${ovp}
    Configure N6700 Power Supply Channel
    ...    ${channel}
    ...    ${voltage}
    ...    ${current_limit}
    ...    output=${FALSE}
    ...    ovp=${ovp}
    ...    ocp=${TRUE}

Enable Output And Verify Voltage
    [Arguments]    ${channel}    ${minimum}    ${maximum}    ${timeout}=5s
    Turn On N6700 Output    ${channel}
    Wait Until N6700 Voltage Is In Range
    ...    ${channel}
    ...    ${minimum}
    ...    ${maximum}
    ...    timeout=${timeout}

Safe Test Teardown
    Shutdown All N6700 Channels
