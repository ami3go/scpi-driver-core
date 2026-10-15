# CORE-ARB-D — N6700 compatibility verification

**Status:** Hardware-free verification PR; the full eight-job matrix must pass
before claiming compatibility. Core remains vendor-independent.

## Immutable revisions

- N6700 driver: `63eaf8f08ea77310039057b7e3e09abeb8306b04`
- Original N6700 core dependency: `ec19ab88906d8e6ac270b30d7615ce7e75dc6a08`
- Hardened core after CORE-ARB-A/B: `3d2c25c5e4e141749478f84631e8215d2984792d`
- Distribution version for this documentation/test change: `0.1.0.dev10`.

The GitHub Actions workflow `.github/workflows/n6700-core-compat.yml` runs
the **same immutable downstream driver commit** against both core revisions,
on CPython 3.10/3.11/3.12/3.13. It installs the selected core directly,
then installs the driver with `--no-deps` specifically to avoid pulling the
driver's old pinned core over the tested version. `pip check` verifies
dependency consistency; this does not change the downstream pin.

The complete non-hardware pytest suite exercises simulator, finite
voltage LIST/UDEF transient APIs, SCPI integration, electronic load,
acquisition, digitizer and scope tests. `hardware` marker tests are
intentionally excluded. Each job publishes JUnit test evidence. Exact pass/
fail/skip counts and any differences between the two commits must be
transcribed from completed CI to this report before merge.

## CORE-ARB-C decision — No numeric vector API in core

A generic SCPI numeric-array serializer would duplicate the existing
`ScpiTextCodec.maximum_command_size` control and instrument-specific
point-count and numeric formatting policies. There is no demonstrated
two-driver reuse requirement. Retain existing binary-block and CSV/text
primitives instead; do not introduce undocumented array fragmentation,
manufacturer-specific waveform classes or binary-upload assumptions.

## Known limitations

1. This matrix is simulator-only, not physical Keysight qualification.
2. Physical VISA/GPIB END/EOI, real binary waveform acceptance, timing,
   model/module-specific Arb behavior and output safety require HIL.
3. The downstream source dependency intentionally remains pinned. A
   future dependency update requires its own versioned PR and full review.
4. If the downstream tests differ between old and new core, the PR must
   remain open until each incompatibility has a reproduction and disposition.

## Gates

- [x] CORE-ARB-A/B merged and core CI matrix green.
- [x] Old/new core SHAs and downstream driver SHA pinned.
- [x] CORE-ARB-C documented without speculative runtime utility.
- [ ] Downstream 8-job compatibility CI passing.
- [ ] Exact counts, regressions and root causes recorded.
- [ ] Final independent technical review and approval for merge.
