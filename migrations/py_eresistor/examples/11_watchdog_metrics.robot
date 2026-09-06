*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Library           Collections
Suite Setup       Connect To EResistor
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Inspect Command Metrics
    Start EResistor Watchdog
    Get EResistor Identity
    ${metrics}=    Get EResistor Metrics
    Log Dictionary    ${metrics}
    Stop EResistor Watchdog
