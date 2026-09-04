*** Settings ***
Documentation     Explicitly guarded raw SCPI diagnostics on the emulator.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    raw    allow_raw_scpi=${False}
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Guarded Raw Query
    Enable Raw SCPI    ENABLE RAW SCPI
    ${idn}=    Raw SCPI Query    *IDN?
    Should Be Equal    ${idn}    NGI,N83624,0,V1.00
