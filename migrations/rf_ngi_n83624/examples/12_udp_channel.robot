*** Settings ***
Documentation     Channel-specific UDP example using port 7001 for channel 1.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Teardown    Close All N83624 Connections

*** Variables ***
${N83624_HOST}    192.168.0.123

*** Test Cases ***
Read Channel One Over UDP
    Open N83624 Channel UDP Connection    udp_ch1    ${N83624_HOST}    1
    ${voltage}=    Measure Channel Voltage    1
    Log    ${voltage} V
