*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Library           Collections
Suite Setup       Connect To EResistor    all_off_on_connect=${True}
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Set Eight Masks Atomically
    @{masks}=    Create List    0001    0003    0007    000F    001F    003F    007F    00FF
    ${actual}=    Set All EResistor Masks    ${masks}
    Log Dictionary    ${actual}
    Open All EResistor Channels
