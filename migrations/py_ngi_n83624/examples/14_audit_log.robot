*** Settings ***
Documentation     Generate JSONL audit evidence for safety-relevant operations.
Library           rf_ngi_n83624.NGI_N83624Library    auto_close_on_suite_end=${False}
Suite Setup       Open N83624 Emulator    audited    audit_log_path=${OUTPUT DIR}${/}ngi_audit.jsonl
Suite Teardown    Close All N83624 Connections

*** Test Cases ***
Create Audit Evidence
    Configure Source Mode    1    3.7    100    output=${False}
    Arm Channel Output    1    ENABLE OUTPUT
    Disable Channel Output    1
