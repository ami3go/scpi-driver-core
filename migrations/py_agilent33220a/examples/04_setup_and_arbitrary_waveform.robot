*** Settings ***
Documentation     Upload and select an arbitrary waveform, and save/restore the instrument
...               setup both to a host file and to instrument memory.
Library           rf_agilent33220a.Agilent33220ALibrary
Library           Collections
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Variables ***
${SETUP_FILE}    ${OUTPUT DIR}/setup.txt

*** Test Cases ***
Upload And Select An Arbitrary Waveform
    # DATA VOLATILE always fills the volatile slot; a name is only assigned
    # by copying it to non-volatile memory afterward (task §6 item 6).
    Load Arbitrary Waveform    ${{[0.0, 0.5, 1.0, 0.5, 0.0, -0.5, -1.0, -0.5]}}
    Copy Arbitrary Waveform To Nonvolatile    MY_SINE_APPROX
    ${names}=    List Arbitrary Waveforms
    List Should Contain Value    ${names}    MY_SINE_APPROX

    Select Arbitrary Waveform    MY_SINE_APPROX
    ${function}=    Get Function
    Should Be Equal    ${function}    USER

    ${attributes}=    Get Arbitrary Waveform Attributes    MY_SINE_APPROX
    Log    Waveform attributes: ${attributes}

Save And Restore Setup To A Host File
    Set Frequency    12345
    Save Setup    ${SETUP_FILE}
    Set Frequency    100
    Restore Setup    ${SETUP_FILE}
    ${frequency}=    Get Frequency
    Should Be Equal As Numbers    ${frequency}    12345

Save And Restore Setup To Instrument Memory
    Set Frequency    6789
    Save Setup To Instrument Memory    1
    Set Frequency    100
    Restore Setup From Instrument Memory    1
    ${frequency}=    Get Frequency
    Should Be Equal As Numbers    ${frequency}    6789
