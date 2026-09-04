*** Settings ***
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    acceptance    max_voltage_v=5.0    max_current_ma=1000.0
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Identify Emulator
    ${idn}=    Identify N83624
    Should Be Equal    ${idn}    NGI,N83624,0,V1.00

Safe Source Configuration And Output
    Configure Source Mode    1    3.7    100    AUTO    output=${False}
    Arm Channel Output    1    ENABLE OUTPUT
    Enable Channel Output    1
    Channel Output Should Be On    1
    Disable Channel Output    1
    Channel Output Should Be Off    1

Measurement Assertion
    Set Emulator Channel Measurement    1    voltage_v=3.70    current_ma=100
    ${voltage}=    Channel Voltage Should Be Within    1    3.7    0.01
    Should Be Equal As Numbers    ${voltage}    3.7

SOC Profile From JSON
    ${steps}=    Set Variable    [{"capacity_mah":10,"voltage_v":3.7,"current_limit_ma":100,"resistance_mohm":1}]
    Configure SOC Profile    1    ${steps}    file_number=1    verify=${False}

Sequence Profile From JSON
    ${steps}=    Set Variable    [{"voltage_v":3.7,"current_limit_ma":100,"resistance_mohm":1,"runtime_s":1}]
    Configure Sequence Profile    1    1    ${steps}    verify=${False}
