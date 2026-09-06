# v26.09 Code Review

## Finding

The driver classified all N677x power modules as supporting `MEAS:POW?`. The manual states that scalar power measurement applies only to N676xA and N678xA SMU modules. On the real N6775A, each attempted power query timed out, generated error 310, and left a query-unterminated error in the queue.

## Change-by-change review

1. **Capability default changed to false:** fail-closed behavior is correct for unknown/basic modules.
2. **N676x/N678x direct power support retained:** matches documented simultaneous voltage/current measurement capability.
3. **N6775A calculated power path:** uses supported `MEAS:VOLT?` and `MEAS:CURR?` queries and preserves the existing return schema.
4. **No exception-based feature probing:** avoids timeouts and error-queue contamination.
5. **Aggregate measurement reuse:** prevents duplicate voltage/current acquisitions when power is calculated.
6. **Channel option normalization:** `""` is now represented as no options instead of a literal quote token.
7. **Robot channel typing:** integer normalization matches list-return types.
8. **Robot variable collision removed:** `${channel_measurement}` no longer shadows `${CHANNEL}`.
9. **Simulator regression:** unsupported N6775A direct power queries are now rejected, preventing simulator-only false confidence.

## Residual risk

Calculated power uses separate voltage and current acquisitions, so it is not a simultaneous sample. This is documented through `power_source=calculated` and is appropriate for N6775A's supported command set.

## Verdict

Approved for physical rerun.
