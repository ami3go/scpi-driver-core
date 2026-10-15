# CORE-ARB-D — N6700 downstream compatibility evidence

**Status:** COMPLETE — software-only verification, 2026-10-15.  
**Core release candidate:** `0.1.0.dev10`.  
**No physical equipment was operated.**

## Immutable versions and commits

| Component | Commit | Meaning |
| --- | --- | --- |
| N6700 original driver | `63eaf8f08ea77310039057b7e3e09abeb8306b04` | Discovered pre-existing contract-lock failure |
| N6700 repaired driver | [`29e8969f`](https://github.com/ami3go/keysight-n6700-driver/commit/29e8969f42713effedf08148f0708cbf04e4217f) | Separate versioned v0.7.8 metadata repair, [PR #19](https://github.com/ami3go/keysight-n6700-driver/pull/19) |
| Original core dependency | `ec19ab88906d8e6ac270b30d7615ce7e75dc6a08` | Immutable pin in N6700 driver |
| Hardened core | [`3d2c25c5`](https://github.com/ami3go/scpi-driver-core/commit/3d2c25c5e4e141749478f84631e8215d2984792d) | Merged CORE-ARB-A/B; v0.1.0.dev9 |
| Compatibility change | Core v0.1.0.dev10 | CI + evidence only; no new vendor logic |

The workflow [`.github/workflows/n6700-core-compat.yml`](../.github/workflows/n6700-core-compat.yml)
uses the **same immutable repaired downstream commit** on both old and new core,
for Python 3.10–3.13, installing the chosen core before the driver via
`pip install --no-deps -e ./downstream`. This prevents the downstream's old
pinned Git dependency from replacing the deliberately selected core. It
verifies `pip check`, then runs the entire N6700 hardware-free pytest suite
(simulator, finite voltage LIST/UDEF transients, acquisition, digitizer,
electronic-load scope, SCPI integration, and additional unit tests). No
downstream checkout files or runtime dependency declarations are changed.
All jobs retain their JUnit XML as Actions artifacts.

## Verified final results

**Final unmodified-source comparison:** [GitHub Actions run 38715855209](https://github.com/ami3go/scpi-driver-core/actions/runs/38715855209)

| Python | Old pinned core | Hardened core | Regression |
| --- | --- | --- | --- |
| 3.10 | 406 passed, 43 skipped, 1 deselected | 406 passed, 43 skipped, 1 deselected | None detected |
| 3.11 | 406 passed, 43 skipped, 1 deselected | 406 passed, 43 skipped, 1 deselected | None detected |
| 3.12 | 406 passed, 43 skipped, 1 deselected | 406 passed, 43 skipped, 1 deselected | None detected |
| 3.13 | 406 passed, 43 skipped, 1 deselected | 406 passed, 43 skipped, 1 deselected | None detected |

All eight jobs **passed** (zero failures). Downstream statement coverage:
approximately 85% (no equivalent 90% branch gate in this downstream suite).
Existing finite voltage LIST/UDEF simulator behavior was covered by the
full unit suite and showed no test regressions; this is not analog qualification.

**Core full verification:** [GitHub Actions run 38715855316](https://github.com/ami3go/scpi-driver-core/actions/runs/38715855316)
passed on Python 3.10, 3.11, 3.12 and 3.13. Each version reported
**1,031 passed, 12 skipped, 0 failed**, with **91.15% combined coverage**
meeting the core's 90% gate; Ruff, Ruff format, strict mypy and packaging
quality gates passed.

**Downstream standalone verification:** [run 38715808417](https://github.com/ami3go/keysight-n6700-driver/actions/runs/38715808417)
for repaired N6700 main at `29e8969f` passed Python 3.10 and 3.13.
Each reported 406 passed and 44 skipped; additional downstream Ruff,
mypy and generated-artifact gates also passed.

### Original baseline failure and resolution

The original downstream N6700 commit had a pre-existing stale SHA-256 in
`ai/ai_contract.lock`; the metadata integrity test failed **equally** on old
and hardened cores ([initial comparison](https://github.com/ami3go/scpi-driver-core/actions/runs/38714765674)).
A first controlled experiment normalized only the lock checksum in ephemeral
CI checkouts; both core versions then passed
([run 38715006134](https://github.com/ami3go/scpi-driver-core/actions/runs/38715006134)).
That temporary workaround was **removed** after the separate N6700
version-incremented metadata-only PR #19 merged into the downstream repository.
The **final** 8-job comparison above requires no normalization, exception,
test deselection beyond the existing hardware marker or source-file modification.
No defect caused by the hardened core was identified.

## CORE-ARB-C — no additional numeric-vector helper

The existing `ScpiTextCodec.maximum_command_size` already supports explicit
larger command budgets. No demonstrated independent second consumer needs a
common formatting helper; point limits, display precision and supported Arb
data formats belong to concrete drivers. Accordingly no numeric-array API,
silent clipping, undocumented array splitting or assumed binary CDW upload
was added.

## Technical review and remaining risks

The two runtime PRs were reviewed for incomplete/malformed binary framing,
exact-byte data handling, injection and timeouts, lock discipline, no-progress
backend calls, faulted-state behavior, non-idempotent replay protection,
versioning and compatibility. Blocking issues found during CI were fixed
and independently rerun within their branches before merging. This
assessment is an internal code-agent technical review, **not an external
human security/audit approval**.

Residual limits: simulator and software CI cannot prove physical SCPI
timing accuracy, ENDie/EOI behavior over vendor VISA/GPIB, real CDW binary
format support, module-specific Arb capabilities, trigger semantics,
output/protection safety or response to hardware disconnection. These
require separately authorized HIL/analog measurement. Third-party backends
which ignore a synchronous timeout cannot be forcibly preempted by Python.
One monotonic in-flight operation deadline does not bound queueing for a lock.

The N6700 project's immutable dependency pin remains unchanged. A later
downstream pin upgrade must use a new, version-incremented N6700 PR with its
own tests and qualification; software compatibility shown here is
not authorization to energize a power module.

## Checklist

- [x] CORE-ARB-A merged: full binary-query and backend I/O deadlines.
- [x] CORE-ARB-B merged: exact outbound scripted binary handling.
- [x] CORE-ARB-C evaluated: no generic vector API justified.
- [x] CORE-ARB-D: exact old/new core and repaired driver revisions pinned.
- [x] All eight downstream hardware-free comparison jobs passing without source workaround.
- [x] Core four-version lint, mypy, pytest, contracts, build and 90% coverage passing.
- [x] Standalone N6700 CI repaired by separately reviewed v0.7.8 PR.
- [x] Regression findings and resolution documented.
- [ ] Real instrument HIL, timing/analog qualifications (deliberately out of scope).
- [ ] Separate downstream core pin upgrade PR (not requested by this core task).
