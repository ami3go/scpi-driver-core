*** Settings ***
Documentation     Connect over TCP and identify the instrument without enabling outputs.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Teardown    Close All N83624 Connections

*** Variables ***
${N83624_HOST}    192.168.0.123
${N83624_PORT}    7000

*** Test Cases ***
TCP Identify
    Open N83624 TCP Connection    bench    ${N83624_HOST}    ${N83624_PORT}
    ${idn}=    Identify N83624
    Log    ${idn}
