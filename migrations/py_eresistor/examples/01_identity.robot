*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Library           Collections
Suite Setup       Connect To EResistor
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Read Device Identity And Status
    ${info}=    Get EResistor Information
    Log Dictionary    ${info}
    Should Not Be Empty    ${info}[identity]
    E-Resistor Should Be Connected
