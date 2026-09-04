# v26.08 — N6775A stale-error startup recovery

- **Python package:** 26.8.0
- **Archive:** `rf_keysight_n6700_v26.08.zip`
- **Internal root:** `rf_keysight_n6700/`

## Problem

A real USB run connected successfully and read the N6700B/N6775A identity, but suite setup failed on the first `OUTP OFF,(@1)` operation. The strict post-write error check drained errors left in the instrument queue by the preceding failed test revision. Because setup had not yet reached `*CLS`, those historical errors were incorrectly attributed to the valid output-off command.

## Changes

- The N6775A self-check now connects with `clear_errors_on_connect=True`.
- Setup sends `*CLS` and confirms an empty error queue before issuing any command that performs strict post-write validation.
- Added a simulator regression that preloads an invalid-header error, connects with startup cleanup enabled, then verifies a safe output-off command and error check succeed.
- Added RFDS-019 static checks that enforce startup cleanup and ordering.
- Updated protocol vectors, release metadata, documentation, contracts, distributions, and package checks.

## Compatibility

The public Robot Framework keyword API remains unchanged. Normal library connections remain non-invasive by default; the error-clearing behavior is enabled only by the dedicated hardware self-check profile or by callers that explicitly set `clear_errors_on_connect=True`.
