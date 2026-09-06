*** Settings ***
Library    rf_eresistor.EResistorLibrary

*** Test Cases ***
Disconnected Keyword Produces Clear Error
    Run Keyword And Expect Error
    ...    E-Resistor is not connected. Call 'Connect To EResistor' first.
    ...    Get EResistor Identity

