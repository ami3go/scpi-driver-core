*** Settings ***
Resource          common.resource
Library           rf_eresistor.EResistorLibrary    host=${ERESISTOR_HOST}
Suite Setup       Connect To EResistor    all_off_on_connect=${True}
Suite Teardown    Disconnect From EResistor

*** Test Cases ***
Set Channel One To Ten Kilohms
    Download EResistor Calibration
    ${result}=    Set EResistor Resistance    1    10000
    Log    mask=${result}[mask], calculated=${result}[calculated_ohm] ohm, error=${result}[error_percent] %
    EResistor Mask Should Be    1    ${result}[mask]

