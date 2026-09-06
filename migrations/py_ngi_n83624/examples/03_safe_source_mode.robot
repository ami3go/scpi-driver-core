*** Settings ***
Documentation     Configure source mode with explicit limits, arming, and safe teardown.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    source    max_voltage_v=5.0    max_current_ma=500
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Safe Source Output Cycle
    Configure Source Mode    1    3.7    100    AUTO    output=${False}
    Arm Channel Output       1    ENABLE OUTPUT
    Enable Channel Output    1
    Channel Output Should Be On    1
    Disable Channel Output  1
    Channel Output Should Be Off    1
