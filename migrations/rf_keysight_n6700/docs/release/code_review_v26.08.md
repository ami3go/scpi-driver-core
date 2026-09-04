# v26.08 Code Review

## Finding

The self-check used `strict_errors=True`, but attempted `OUTP OFF` before normalizing the instrument error queue. A stale error queue therefore caused a valid command to fail during suite setup. The trace showed successful USB connection and valid responses for `*IDN?`, module discovery, `OUTP?`, `VOLT?`, `CURR?`, `VOLT:PROT?`, and `CURR:PROT:STAT?`; the reported errors were historical queue entries.


## Change-by-change review

1. `clear_errors_on_connect=True`: appropriate for the dedicated conformance profile; normal connections retain the non-invasive default.
2. Early `*CLS`: correct per the programmer’s reference because it clears the error queue and status event registers without changing programmed output settings.
3. Empty-queue assertion: proves startup normalization completed before strict command checks begin.
4. Simulator regression: reproduces a stale undefined-header error and verifies a subsequent output-off command succeeds.
5. RFDS-019 validator checks: prevent startup-order regression in future releases.

## Correction review

- Startup error draining occurs during connection.
- `*CLS` executes before the first strict-checked write.
- The queue is explicitly verified empty after `*CLS`.
- Default library connections still preserve existing instrument status unless explicitly requested otherwise.
- Regression coverage reproduces a preloaded stale error and proves recovery.

## Residual risk

A real instrument can generate a new error after startup cleanup. Such an error must still fail the strict self-check, which is the intended behavior.

## Verdict

Approved for hardware retest.
