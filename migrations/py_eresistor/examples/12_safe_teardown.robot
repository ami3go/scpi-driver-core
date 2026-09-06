*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor    all_off_on_connect=${True}
Suite Teardown    Safe Suite Shutdown

*** Test Cases ***
Operate With Explicit Safe Teardown
    Set EResistor Mask    1    0001
    EResistor Mask Should Be    1    0001

*** Keywords ***
Safe Suite Shutdown
    Run Keyword And Ignore Error    Open All EResistor Channels
    Disconnect From EResistor

