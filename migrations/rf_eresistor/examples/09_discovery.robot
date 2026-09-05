*** Settings ***
Library    rf_eresistor.EResistorLibrary

*** Test Cases ***
Discover Boards On Lab Subnet
    ${boards}=    Discover EResistor Boards    ${SUBNET}
    Log Many    @{boards}

*** Variables ***
${SUBNET}    192.168.0.0/24

