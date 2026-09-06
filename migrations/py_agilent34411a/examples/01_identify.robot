*** Settings ***
Documentation     Connect to an Agilent 34411A (or the bundled simulator) and read its identity.
...               Run against the simulator:
...                   robot --outputdir results examples/01_identify.robot
...               Run against real hardware, override RESOURCE:
...                   robot --outputdir results --variable RESOURCE:USB0::0x0957::0x0618::<serial>::INSTR
...                   --variable SIMULATED:False examples/01_identify.robot
Library           rf_agilent34411a.Agilent34411ALibrary
Suite Teardown    Disconnect

*** Variables ***
${RESOURCE}     ${None}
${SIMULATED}    ${TRUE}

*** Test Cases ***
Identify The Multimeter
    ${state}=    Connect    resource=${RESOURCE}    simulated=${SIMULATED}
    Should Be True    ${state}[connected]
    Log    Connected: ${state}

    ${identity}=    Get Identity
    Log    Identity: ${identity}
    Should Not Be Empty    ${identity}

    ${ok}=    Check Communication
    Should Be True    ${ok}
