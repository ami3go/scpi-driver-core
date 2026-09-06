*** Settings ***
Documentation     Configure the LAN interface identity and the analog interface's
...               reference range / REM-SB pin behavior (Gate 3). These are ordinary
...               device-configuration commands like the Gate 2 ones in
...               02_set_values_and_measure.robot — no special safety guard beyond the
...               instrument's universal remote-control gating.
Library           rf_ea_ps9000t.EaPs9000TLibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure LAN Identity
    Set LAN Hostname    bench-3-supply
    Set LAN Domain    lab.example.com
    Set LAN IP Address    192.168.1.50
    Set LAN Subnet Mask    255.255.255.0
    Set LAN Gateway    192.168.1.1

    ${hostname}=    Get LAN Hostname
    ${ip}=    Get LAN IP Address
    Log    ${hostname} at ${ip}

    # Port 502 is reserved for ModBus TCP and rejected client-side before any
    # device write.
    Run Keyword And Expect Error    *ValidationError*    Set LAN Control Port    502
    Set LAN Control Port    6000
    ${port}=    Get LAN Control Port
    Should Be Equal As Integers    ${port}    6000

Configure Analog Interface
    Set Analog Reference Range    5
    ${range}=    Get Analog Reference Range
    Log    Analog reference range: ${range} V

    # REM-SB pin behavior: AUTO lets a previously-enabled output be switched
    # back on when the pin's hold condition clears, not just switched off.
    Set Analog REMSB Level    NORMAL
    Set Analog REMSB Action    AUTO
    ${action}=    Get Analog REMSB Action
    Should Be Equal    ${action}    AUTO
