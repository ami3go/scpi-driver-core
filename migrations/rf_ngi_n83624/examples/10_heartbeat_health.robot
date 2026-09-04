*** Settings ***
Documentation     Start heartbeat and inspect communication health.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    heartbeat
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Heartbeat Health
    Start N83624 Heartbeat    interval_s=0.1    fail_after=3
    Sleep    0.25s
    ${health}=    Get N83624 Communication Health
    Log    ${health}
    Stop N83624 Heartbeat
