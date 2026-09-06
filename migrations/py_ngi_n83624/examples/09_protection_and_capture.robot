*** Settings ***
Documentation     Configure OCP, OVP, OPP, and capture rate.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    protection
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Configure Protection
    Set Channel Protection Limits    1    450    4.5    2000
    ${rate}=    Set Channel Capture Rate    1    MEDIUM_120MS
    Should Be Equal    ${rate}    MEDIUM_120MS
