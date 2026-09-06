*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Load Cached Calibration And Preview
    ${cal}=    Load EResistor Calibration    ${CALIBRATION_FILE}
    ${result}=    Find Closest EResistor Resistance    1    10000
    Log    ${result}

*** Variables ***
${CALIBRATION_FILE}    eresistor_calibration.json

