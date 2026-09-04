# Major Fixes Applied During Implementation Review

## MF-01 — Shutdown aborted after first channel failure

**Severity:** Critical safety robustness  
**Original behavior:** `all_outputs_off()` and close-time loops stopped on the first exception. Channels after the failed one might never receive an OFF command.  
**Correction:** Attempt all 24 channels, collect failures, and raise an aggregated `SafetyError` after all attempts.  
**Evidence:** `test_all_outputs_off_attempts_remaining_channels_after_failure` injects a channel-2 failure and verifies channel 24 is still commanded OFF.

## MF-02 — Heartbeat close lock ordering

**Severity:** Major reliability  
**Original behavior:** `close()` held the driver lock while requesting heartbeat stop and joining the thread. A heartbeat query waiting for the same lock could delay shutdown until join timeout.  
**Correction:** Stop/join heartbeat before acquiring the driver lock for shutdown.

## MF-03 — Misnamed monotonic timestamps used wall clock

**Severity:** Major timeout/diagnostic correctness  
**Original behavior:** `last_*_monotonic_s` fields were populated with `time.time()`.  
**Correction:** Use `time.monotonic()`.  
**Evidence:** monotonic-bound unit test.

## MF-04 — No Robot-level output authorization state

**Severity:** Critical misuse prevention  
**Original behavior:** The Python API required limits but the default null interlock was permissive, and Robot scripts had no explicit arming state.  
**Correction:** Added per-session armed-channel registry. Output enable requires finite limits and exact confirmation `ENABLE OUTPUT`. Limit changes and recovery clear arming.

## MF-05 — Raw SCPI bypass lacked Robot-level guard

**Severity:** Major safety/API integrity  
**Correction:** Raw query/write disabled by default and enabled only with exact confirmation `ENABLE RAW SCPI`.

## MF-06 — Emulator did not implement aggregate measurements

**Severity:** Major offline coverage  
**Original behavior:** Multi-channel measurement examples failed because aggregate queries returned one default value.  
**Correction:** Emulator parses selected-channel voltage/current/power queries and returns ordered CSV values.

## MF-07 — Example suites were not all executable

**Severity:** Major deliverable quality  
**Original behavior:** Examples used `Log Dictionary` without importing `Collections`.  
**Correction:** Replaced with built-in `Log`; reran all offline suites successfully.
