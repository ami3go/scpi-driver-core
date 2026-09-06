*** Settings ***
Documentation     Connect to an EA-PS 9000 T (or the bundled simulator) and demonstrate
...               explicit remote-control acquisition — unlike every other driver in this
...               repository, this instrument requires an explicit lock request before any
...               value-changing command is honored (task §6 item 1), and the request can
...               be refused.
...               Run against the simulator:
...                   robot --outputdir results examples/01_identify_and_remote_control.robot
...               Run against real hardware, override RESOURCE (USB/RS232/Ethernet all work
...               as a VISA resource string):
...                   robot --outputdir results --variable RESOURCE:TCPIP0::192.168.0.2::5025::SOCKET
...                   --variable SIMULATED:False examples/01_identify_and_remote_control.robot
Library           rf_ea_ps9000t.EaPs9000TLibrary
Suite Teardown    Disconnect

*** Variables ***
${RESOURCE}     ${None}
${SIMULATED}    ${TRUE}

*** Test Cases ***
Identify And Confirm Remote Control Was Acquired
    ${state}=    Connect    resource=${RESOURCE}    simulated=${SIMULATED}
    Should Be True    ${state}[connected]
    Log    Connected: ${state}

    ${identity}=    Get Identity
    Log    Identity: ${identity}
    Should Not Be Empty    ${identity}

    ${ok}=    Check Communication
    Should Be True    ${ok}

    # Connect already acquired remote control (task §6 item 1) — confirm it here.
    ${owner}=    Get Remote Control Owner
    Should Be Equal    ${owner}    REMOTE
