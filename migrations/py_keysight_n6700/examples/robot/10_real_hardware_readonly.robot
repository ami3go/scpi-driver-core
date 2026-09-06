*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Real N6700 If Configured
Suite Teardown    Disconnect All N6700

*** Variables ***
${N6700_RESOURCE}    NOT_SET

*** Test Cases ***
Read Identity And Installed Modules
    ${identity}=    Get N6700 Identity
    Log    ${identity}
    ${modules}=    Discover N6700 Modules
    Log    ${modules}

*** Keywords ***
Connect To Real N6700 If Configured
    Skip If    '${N6700_RESOURCE}' == 'NOT_SET'    Supply --variable N6700_RESOURCE:<visa-resource>
    Connect To N6700 Via VISA    ${N6700_RESOURCE}    hardware
