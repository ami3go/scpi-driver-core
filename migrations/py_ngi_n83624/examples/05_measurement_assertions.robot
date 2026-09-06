*** Settings ***
Documentation     Use deterministic readbacks and Robot-friendly assertions.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    measure
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Voltage And Current Are In Range
    Set Emulator Channel Measurement    1    voltage_v=3.705    current_ma=99.5
    Channel Voltage Should Be Within    1    3.7    0.01
    Channel Current Should Be Within    1    100    1.0
