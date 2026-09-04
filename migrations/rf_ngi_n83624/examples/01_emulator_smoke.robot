*** Settings ***
Documentation     Offline smoke test using the deterministic emulator.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    emu
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Identify And Read Channel
    ${idn}=    Identify N83624
    Log    ${idn}
    Set Emulator Channel Measurement    1    voltage_v=3.70    current_ma=100    power_w=0.37
    ${measurement}=    Measure Channel    1
    Log    ${measurement}
