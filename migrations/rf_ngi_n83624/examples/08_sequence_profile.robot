*** Settings ***
Documentation     Program a sequence table from JSON while output remains off.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    sequence
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Program Sequence
    ${steps}=    Set Variable    [{"voltage_v":3.0,"current_limit_ma":100,"resistance_mohm":10,"runtime_s":1},{"voltage_v":4.2,"current_limit_ma":100,"resistance_mohm":10,"runtime_s":1}]
    Configure Sequence Profile    1    1    ${steps}    file_cycle=2    output=${False}    verify=${False}
