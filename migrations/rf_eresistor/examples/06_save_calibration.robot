*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Download And Save Calibration
    Download EResistor Calibration
    Save EResistor Calibration    ${OUTPUT DIR}${/}eresistor_calibration.json
    File Should Exist    ${OUTPUT DIR}${/}eresistor_calibration.json

*** Keywords ***
File Should Exist
    [Arguments]    ${path}
    ${exists}=    Evaluate    __import__('pathlib').Path(r'''${path}''').is_file()
    Should Be True    ${exists}

