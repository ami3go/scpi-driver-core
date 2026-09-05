*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor    all_off_on_connect=${True}
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Set Selected Channels Atomically
    Download EResistor Calibration
    &{values}=    Create Dictionary    1=1000    2=10000    4=100000
    ${results}=    Set Multiple EResistor Resistances    ${values}    atomic=${True}
    Log Many    @{results}

