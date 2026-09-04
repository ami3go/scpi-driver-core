*** Settings ***
Documentation     Calibration (behind a dedicated two-tier guard) and LAN identity
...               configuration (Gate 3). Run against the simulator:
...                   robot --outputdir results examples/05_calibration_and_lan_configuration.robot
...               Run against real hardware, override RESOURCE:
...                   robot --outputdir results --variable RESOURCE:USB0::0x0957::0x0618::<serial>::INSTR
...                   --variable SIMULATED:False examples/05_calibration_and_lan_configuration.robot
...
...               Calibration writes real, persistent calibration constants on real hardware —
...               never run the calibration test case above against a production instrument
...               unless you mean to recalibrate it.
Library           rf_agilent34411a.Agilent34411ALibrary
Suite Setup       Connect    resource=${RESOURCE}    simulated=${SIMULATED}
Suite Teardown    Disconnect

*** Variables ***
${RESOURCE}     ${None}
${SIMULATED}    ${TRUE}

*** Test Cases ***
Calibration Is Blocked Until The Guard Is Enabled
    Run Keyword And Expect Error    *ValidationError*    Run Full Calibration
    Enable Calibration Mode    ENABLE CALIBRATION
    Run Keyword And Expect Error    *DeviceError*    Run Full Calibration
    Unlock Calibration    AT34411A
    ${passed}=    Run Full Calibration
    Log    Calibration passed: ${passed}
    Lock Calibration

Configure LAN Identity
    Set LAN Hostname    bench-3-dmm
    Set LAN Domain    lab.example.com
    Set LAN IP Address    10.0.0.5
    Set LAN Subnet Mask    255.255.255.0
    Set LAN Gateway    10.0.0.1

    ${hostname}=    Get LAN Hostname
    ${ip}=    Get LAN IP Address
    Log    ${hostname} at ${ip}

    ${mac}=    Get LAN MAC Address
    Log    MAC address: ${mac}
