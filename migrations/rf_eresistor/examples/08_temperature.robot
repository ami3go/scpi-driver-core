*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor    all_off_on_connect=${True}
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Emulate Twenty Five Degrees
    Download EResistor Calibration
    Load EResistor Temperature Table    1    ${CURDIR}${/}ntc_10k.csv
    ${result}=    Set EResistor Temperature    1    25    interpolation=log_resistance
    Log    ${result}

