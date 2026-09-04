*** Settings ***
Documentation     Configure amplitude modulation, a frequency sweep with the marker
...               keywords, and a burst — the three signal-shaping modes beyond a plain
...               continuous output.
Library           rf_agilent33220a.Agilent33220ALibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Amplitude Modulation
    Configure Amplitude Modulation    SINusoid    100    50
    Enable Amplitude Modulation
    Disable Amplitude Modulation

Frequency Sweep With Marker
    Configure Frequency Sweep    start=100    stop=10000    spacing=LINear    time_s=2.0
    Enable Sweep
    Set Sweep Marker Frequency    5000
    Enable Sweep Marker
    ${marker_frequency}=    Get Sweep Marker Frequency
    Log    Marker frequency: ${marker_frequency} Hz
    Disable Sweep Marker
    Disable Sweep

Burst
    Set Trigger Source    BUS
    Configure Burst    mode=TRIGgered    cycles=5    period=0.01
    Enable Burst
    Trigger Now
    Disable Burst
