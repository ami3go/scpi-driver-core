# CORE-ARB-D — N6700 compatibility verification

**Status:** Hardware-free compatibility matrix completed on 2026-10-15. Eight
jobs pass after correcting one known, pre-existing generated-lock mismatch
in the **ephemeral CI checkout only**. Unmodified downstream source still
fails one unrelated metadata-integrity test; see release blocker below.
Core remains vendor-independent.

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
intentionally excluded. Each job publishes JUnit test evidence. The resulting pass/fail/skip counts and baseline metadata deviation are
reported below; see the verified CI run links.

## Verified CI results

- **Original untouched driver checkout:** GitHub Actions run
  [38714765674](https://github.com/ami3go/scpi-driver-core/actions/runs/38714765674)
  failed across all eight jobs with the same pre-existing issue:
  `tests/unit/test_ai_contract.py::test_ai_contract_lock_hash_matches_the_contract_file`.
  Representative result: **405 passed, 43 skipped, 1 deselected, 1 failed**.
  It occurs against **both** original and hardened cores.
- **Ephemeral metadata normalization only:** GitHub Actions run
  [38715006134](https://github.com/ami3go/scpi-driver-core/actions/runs/38715006134)
  passed **8/8** jobs across Python 3.10–3.13 and both immutable core SHAs.
  Each job: **406 passed, 43 skipped, 1 deselected, 0 failed**;
  downstream statement coverage **85%** (the downstream suite does not impose
  the core's 90% branch-coverage requirement).
- **Core quality matrix:** GitHub Actions run
  [38715006776](https://github.com/ami3go/scpi-driver-core/actions/runs/38715006776):
  **4/4** Python-version jobs successful for this documentation-only PR.
  Previous runtime CORE-ARB-A/B changes passed their own 90% core coverage gates.

The comparison shows **no software-behavior regressions** in the downstream
hardware-free suite. We do **not** claim that the untouched N6700 checkout
passes its own quality gate. Compatibility evidence is conditional on
normalizing only the stale generated-lock SHA in the test workspace; no
runtime driver files, waveform logic, or pinned dependency are modified.

### Remaining gate before PR #10 can merge

The downstream repository needs to regenerate and commit
`ai/ai_contract.lock` so its `contract_sha256` matches the current
`ai/ai_contract.yaml`, and rerun its normal CI against the unmodified
committed source. Because any N6700 repository change must be versioned
and separately reviewed, remediation belongs in a dedicated downstream PR.
After that repair is merged, rerun this compatibility matrix pinned to the
reviewed repaired downstream SHA **without** the temporary lock
normalization and record all green results before considering this PR
mergeable. Do not relax this release gate silently.

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
- [x] Downstream eight-job isolated compatibility matrix passing after temporary generated-lock normalization.
- [x] Exact counts, zero core-induced regressions and pre-existing lock root cause recorded.
- [ ] Downstream regenerated lock committed by separate versioned PR; untouched-source suite green.
- [ ] Retest pinned repaired driver without temporary generated-lock normalization.
- [ ] Independent external approval (currently technical self-review only); PR #10 merge gate.
