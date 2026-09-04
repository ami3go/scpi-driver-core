*** Settings ***
Documentation     Program an SOC table from JSON while output remains off.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    soc
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Program SOC Profile
    ${steps}=    Set Variable    [{"capacity_mah":0,"voltage_v":3.0,"current_limit_ma":100,"resistance_mohm":10},{"capacity_mah":1000,"voltage_v":4.2,"current_limit_ma":100,"resistance_mohm":10}]
    Configure SOC Profile    1    ${steps}    file_number=1    start_voltage_v=3.0    output=${False}    verify=${False}
