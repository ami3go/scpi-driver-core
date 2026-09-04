*** Settings ***
Documentation     Configure charge mode while keeping output disabled.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    charge    max_voltage_v=5.0    max_current_ma=500
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Configure Charge Safely
    Configure Charge Mode    1    4.2    200    10    output=${False}
    ${mode}=    Get Channel Mode    1
    Should Be Equal    ${mode}    CHARGE
