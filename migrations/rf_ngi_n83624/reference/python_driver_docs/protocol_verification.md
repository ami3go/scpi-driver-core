# Protocol Verification Notes

This document records items that require verification on real hardware before production use.

| Item | Status | Notes |
|---|---|---|
| TCP socket lifetime | Not verified | Confirm whether socket stays open indefinitely and how device behaves after idle timeout. |
| UDP query response framing | Not verified | Confirm response terminator and packet size for all query types. |
| Per-channel UDP ports 7001..7024 | Implemented conservatively | Driver restricts high-level access to the matching channel. |
| `MEASure0:CAPRate` global setting | Experimental | Methods require `experimental_ok=True`. |
| `SOC<n>:EDIT:FILE` vs `RILE` | Interpreted as `FILE` | Based on task/manual inconsistency notes; verify on hardware. |
| `*CLS`, `*ESR?`, `*STB?` | Experimental | Methods require `experimental_ok=True` because manual does not clearly document them. |
| CAN ID/rate setters | Not implemented | Manual clearly shows query forms only. |
| Error queue command | Not implemented | No documented `SYSTem:ERRor?` command in the supplied task/manual review. |
