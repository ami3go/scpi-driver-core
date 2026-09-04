*** Settings ***
Documentation     Configure the output via the low-level keywords, then via the guarded
...               Configure Output/Enable Output pair, and demonstrate the amplitude/offset
...               safety validation (task §6 item 4).
Library           rf_agilent33220a.Agilent33220ALibrary
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Test Cases ***
Configure Output Via Low Level Keywords
    Set Function    SINusoid
    Set Frequency    1000
    Set Amplitude    1.0
    Set Offset    0.0
    ${settings}=    Get Output Settings
    Log    Output settings: ${settings}

Configure Output Never Enables The Output Implicitly
    # task §6 item 1: APPLy silently enables the output as a documented side
    # effect; Configure Output restores whatever state the output was in
    # beforehand unless enable_output=True is explicitly passed.
    Configure Output    SQUare    2000    2.0    0.0
    ${enabled}=    Is Output Enabled
    Should Not Be True    ${enabled}

    Configure Output    SQUare    2000    2.0    0.0    enable_output=${TRUE}
    ${enabled}=    Is Output Enabled
    Should Be True    ${enabled}
    Disable Output

Amplitude Offset Safety Validation
    # Vpp < 2*(Vmax-|Voffset|) is checked before any device I/O and raises
    # Agilent33220ASafetyError, not a generic validation error.
    Run Keyword And Expect Error    *SafetyError*    Set Amplitude    100
