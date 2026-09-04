# rf-ngi-n83624 v26.02

`rf-ngi-n83624` is a Robot Framework keyword library for the NGI N83624 24-channel battery/cell simulator.

The library adds Robot-oriented session management and safety controls around the supplied typed Python SCPI driver:

- TCP, UDP, per-channel UDP, serial, and emulator transports.
- Explicit finite limits and output arming.
- Source, charge, SOC, and sequence workflows.
- Measurements, assertions, wait keywords, heartbeat, recovery, and audit logs.
- Best-effort all-channel output shutdown.

Release v26.02 adds an RFDS-008 structured evidence engine (`rf_ngi_n83624/evidence.py`,
one run per connection alias) and a real-hardware RFDS-019 conformance suite covering all
62 public keywords. See [Logging and evidence](logging-and-evidence.md) — this is a deeper,
always-on-by-default complement to the pre-existing opt-in `audit_log_path` trace, not a
replacement for it.

!!! warning
    v26.02 has offline test evidence but has not been qualified against the user's exact N83624 hardware and firmware. Complete the hardware qualification plan before production use.
