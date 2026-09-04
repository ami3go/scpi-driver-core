*** Settings ***
Library    rf_keysight_n6700.KeysightN6700Library
Suite Setup       Connect To Simulated N6700
Suite Teardown    Disconnect All N6700

*** Test Cases ***
Power Supply Workflow
    Configure N6700 Power Supply Channel    1    5V    1A    output=${TRUE}
    N6700 Voltage Should Be    1    5V    1mV
    N6700 Current Should Be    1    500mA    1mA
    N6700 Power Should Be      1    2.5W    1mW

SMU Workflow
    Configure N6700 SMU Current Priority    2    100mA    3.3V
    ${mode}=    Get N6700 SMU Mode    2
    Should Be Equal    ${mode}    current

Load Workflow
    Configure N6700 Load CC    3    250mA    input_on=${TRUE}
    ${state}=    Get N6700 Load Input State    3
    Should Be True    ${state}
