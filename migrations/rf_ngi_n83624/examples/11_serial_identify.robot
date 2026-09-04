*** Settings ***
Documentation     RS232 identification example; adjust COM port for the bench.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Teardown    Close All N83624 Connections

*** Variables ***
${SERIAL_PORT}    COM5
${BAUDRATE}       115200

*** Test Cases ***
Serial Identify
    Open N83624 Serial Connection    serial    ${SERIAL_PORT}    ${BAUDRATE}
    ${idn}=    Identify N83624
    Log    ${idn}
