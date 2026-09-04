*** Settings ***
Documentation     Fetch a waveform, save a screen image, export a CSV, save/restore
...               the instrument setup, and demonstrate instrument-side waveform
...               save/recall via reference memory (Gate 3).
Library           rf_tbs1000c.Tbs1000cLibrary
Library           OperatingSystem
Suite Setup       Connect    simulated=${TRUE}
Suite Teardown    Disconnect

*** Variables ***
${SCREEN_IMAGE}    ${OUTPUT DIR}/example_screen.png
${WAVEFORM_CSV}     ${OUTPUT DIR}/example_waveform.csv
${SETUP_FILE}       ${OUTPUT DIR}/example_setup.txt
${WAVEFORM_ON_INSTRUMENT}    ${OUTPUT DIR}/example_waveform_on_instrument.csv

*** Test Cases ***
Capture A Waveform And Save Evidence
    ${waveform}=    Get Waveform    1
    Log    Captured ${{len($waveform["time_s"])}} points

    Save Screen Image    ${SCREEN_IMAGE}
    File Should Exist    ${SCREEN_IMAGE}

    Save Waveform To CSV    ${WAVEFORM_CSV}    1
    File Should Exist    ${WAVEFORM_CSV}

Save And Restore A Known Configuration
    Set Channel Scale    1    0.2
    Save Setup    ${SETUP_FILE}

    Set Channel Scale    1    5.0
    Restore Setup    ${SETUP_FILE}

    ${scale}=    Get Channel Scale    1
    Should Be Equal As Numbers    ${scale}    0.2

Instrument-Side Waveform Save And Recall
    # Save channel 1 straight into the instrument's own reference memory —
    # no host file transfer, distinct from 'Save Waveform To CSV' above.
    Save Waveform To Reference Memory    1    1

    # Round trip through a host file: save channel 1 to the instrument's own
    # filesystem and pull it to the host, then push that same file back onto
    # the instrument and load it into a second reference memory location.
    Save Waveform To CSV On Instrument    ${WAVEFORM_ON_INSTRUMENT}    1
    File Should Exist    ${WAVEFORM_ON_INSTRUMENT}
    Recall Waveform From Host File    ${WAVEFORM_ON_INSTRUMENT}    2
