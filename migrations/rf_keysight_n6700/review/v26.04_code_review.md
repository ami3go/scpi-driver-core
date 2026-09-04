# Code review — v26.04

## Scope

Reviewed `keysight_n6700/driver.py`, the N6775A conformance suite/resources/data, runners, static validator, evidence postprocessor, tests, and documentation.

## Change-by-change review

| Change | Finding | Severity | Corrective action | Residual risk | Test/evidence |
|---|---|---:|---|---|---|
| SCPI JSONL trace | Trace is recorded at the transport boundary for writes, queries, responses, exceptions, and duration. | NOTE | Added atomic append-style record creation and unit test. | Multiple processes must not share one trace file. | `test_protocol_audit_trace_records_write_query_and_response` |
| Real-device suite | Applicable N6775A PSU/session/measurement/protection calls have explicit response/read-back oracles. | NOTE | Added 21 test cases and 44 vectors. | Exact firmware/model differences can still expose unsupported commands; this is an intended conformance failure. | Robot suite and protocol vectors |
| Unsupported APIs | N6775A cannot execute SMU/load operations. | NOTE | Added expected-failure calls proving rejection before SCPI transmission. | Capability classification depends on correct module identification. | Test 16 |
| Active output | Energization could be unsafe. | CRITICAL (controlled) | Disabled by default; low limits, OVP/OCP, explicit opt-in, per-test safe-off, suite shutdown. | Software cannot replace fixture/interlock protection. | Test 18 and teardown |
| Reset | `*RST` can alter configuration. | MAJOR (controlled) | Disabled by default and executed output-off only. | Device-specific reset defaults must be reviewed. | Test 17 |
| Error/recovery | An invalid command intentionally modifies error queue. | MINOR | Clear first, verify non-zero error, then prove `*IDN?` recovery and empty queue. | Firmware-specific error text is not required. | Test 14 |
| Evidence generation | RFDS-019 requires traceable reports. | NOTE | Added postprocessor for inventory, coverage, vectors, traces, environment, identity, and summary. | Postprocessor depends on valid Robot `output.xml`. | `summarize_n6775a_self_check.py` |

## Architecture assessment

The Robot suite uses only the public library API. Protocol serialization remains in the core/channel classes. Trace capture is below the adapter at the driver/transport boundary. Safety ownership remains in the library/session shutdown and suite teardown.

## Final assessment

No unresolved Critical or Major implementation finding. Physical N6775A acceptance remains pending and must not be inferred from simulator/static results.
