*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor    all_off_on_connect=${True}
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Activate Q16 On Channel One Then Open It
    Set EResistor Mask    1    0001
    EResistor Mask Should Be    1    0001
    Set EResistor Mask    1    0000
    EResistor Mask Should Be    1    0000

