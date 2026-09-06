*** Settings ***
Documentation     Read several channels in one command path.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    multi
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Measure Selected Channels
    Set Emulator Channel Measurement    1    voltage_v=3.1
    Set Emulator Channel Measurement    2    voltage_v=3.2
    Set Emulator Channel Measurement    3    voltage_v=3.3
    ${values}=    Measure Voltage Channels    1,2,3
    Log    ${values}
