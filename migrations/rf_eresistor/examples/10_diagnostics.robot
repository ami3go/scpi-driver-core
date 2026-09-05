*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Read Status And Error Queue
    ${status}=    Get EResistor Status
    ${error}=     Get EResistor Error
    ${state}=     Send EResistor SCPI Query    STATE?
    Log Many    ${status}    ${error}    ${state}

