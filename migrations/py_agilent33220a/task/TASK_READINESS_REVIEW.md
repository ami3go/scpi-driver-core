# Task Readiness Review

**Reviewed task:** Robot Framework driver for Agilent 33220A
**Reviewed revision:** 26.01-draft
**Review date:** 2026-08-01

## Initial task assessment

The first drafted version was grounded in the real Agilent 33220A User's Guide (part
9018-04437) throughout: every command cited (`APPLy`, `FUNCtion`/`FREQuency`/`VOLTage`,
`AM`/`FM`/`PM`/`FSKey`/`PWM`, `SWEep`, `BURSt`, `DATA`/`DATA:DAC`, `*SAV`/`*RCL`, `*LRN?`)
came from the source manual, and it correctly identified the instrument's one real
safety-relevant gotcha — `APPLy` silently re-enabling the output even though `OUTPut`
itself defaults OFF — from the command's actual detailed description, not just its summary
listing. The RFDS-002 canonical connection keywords were specified as the primary API from
the outset, and the architecture correctly collapsed GPIB/USB/LAN into a single VISA
backend rather than assuming three separate transports the way an under-researched pass
might have.

It had four concrete defects, all found by cross-checking §2's own command inventory
against what the later keyword sections (§7-§12) and exception hierarchy (§5.2) actually
did with it.

| Area | Initial score | Main gap |
|---|---:|---|
| Instrument grounding | 9.6 | — |
| Connection lifecycle | 9.5 | — |
| Command inventory vs. keyword coverage | 7.0 | `MARKer` inventoried but never became a keyword |
| Front-panel/operator-interference commands | 5.0 | `SYSTem:KLOCk` (lockout) not inventoried at all, despite being directly relevant to unattended automated runs |
| Exception hierarchy | 8.0 | `Agilent33220ASafetyError` declared but never referenced anywhere |
| Document mechanics | 8.5 | One malformed bullet (missing `-` marker) in §13, merging two unrelated simulator requirements into one line |
| Signal-integrity/safety requirements | 9.3 | — |
| Testing | 9.0 | — |
| Packaging/versioning | 9.5 | — |
| Documentation/examples | 9.0 | — |
| Acceptance criteria/traceability | 8.5 | Didn't reflect the safety-error-type distinction |

**Initial readiness score: 8.4/10 — well-grounded and architecturally sound, but not ready
to hand to Gate 2 as-is: a keyword gap existed between what was researched and what was
specified, and a declared exception type had no defined trigger, which would have forced an
implementer to either guess or silently drop it.**

## Corrections applied

1. Added `SYSTem:KLOCk[:STATe]`/`:EXCLude`, `DISPlay {OFF|ON}`/`:TEXT`/`:CLEar`,
   `SYSTem:BEEPer` to §2's command inventory. Front-panel lockout in particular is a real,
   valuable feature for this exact use case — an unattended automated run where an operator
   standing at the bench could otherwise hand-edit a live setting.
2. Added `Lock Front Panel` / `Unlock Front Panel` / `Is Front Panel Locked` and
   `Set/Clear Display Text`, `Enable/Disable Display` keywords to §8, with a note
   recommending front-panel lock in every suite that changes output settings.
3. Added the `MARKer:FREQuency`/`MARKer {OFF|ON}` keywords to §9 (sweep section), where
   they belong per the manual's own grouping — closing the gap between what §2 inventoried
   and what §9 actually specified as keywords.
4. Fixed the malformed §13 bullet (a missing `-` had silently merged the amplitude/offset
   validation test requirement and the function-limit "Settings conflict" simulation
   requirement into a single bullet, obscuring that they're two separate things the
   simulator must support).
5. Wired up `Agilent33220ASafetyError`: reclassified the amplitude/offset limit check (§6
   item 4) from the generic validation error to this safety-specific type, matching
   RFDS-007's `DriverSafetyError` → `LimitViolation` family — this is a documented physical
   signal-integrity constraint, not an arbitrary argument-shape check, so it deserves its
   own error class rather than being indistinguishable from "you passed a string where a
   number was expected." Updated both §6 item 4 and the corresponding §14.1 test (item 4)
   and §18 acceptance criterion for consistency.

## Second review pass — checking the first pass's own corrections for follow-through

RFDS-010's own review checklist (13 weighted domains) was considered as a possible scoring
rubric for this second pass, then rejected: it's a *release*-readiness rubric for shipped
code (transport correctness, test coverage, AI contracts, hardware qualification, security/
provenance) — applied to a pre-code task document, most of its domains would just read
"N/A, no code exists yet," which would be a meaningless exercise. `rf_ngi_n83624`'s
task-readiness-review precedent (custom domains scoped to what a *task document* actually
contains) remains the right instrument here, so this pass re-applied that same method more
skeptically rather than switching rubrics.

A full re-read specifically checked whether the first pass's own corrections were fully
threaded through the rest of the document — a common failure mode for review corrections is
fixing the immediate defect but not propagating it everywhere it should show up. Two
follow-through gaps were found:

1. The first pass added front-panel-lock, display-text, and sweep-marker keywords to §8/§9,
   but never added corresponding coverage to §14.1's test list, §14.2's acceptance-test
   description, or §18's acceptance checklist — the new keywords existed but weren't
   actually required to be tested. Fixed: added §14.1 items 13-14, extended §14.2's
   coverage description, and updated §18.
2. §2 inventoried `MEMory:STATe:VALid?` but §11 never used it — `Restore Setup From
   Instrument Memory` would have called `*RCL` on a possibly-never-saved slot without
   checking first, which is exactly the "silently reconfiguring instead of failing clearly"
   failure mode §14.1 item 11 already tests for on the *file-based* restore path, just
   missed on the *instrument-memory* restore path. Fixed: added the validity check to §11,
   a test case to §14.1 item 12, and simulator support to §13.

Both are the same category of defect as the first pass's dead `Agilent33220ASafetyError`
declaration: something added in isolation without checking whether it needed to exist
consistently everywhere the document's own conventions already required. No new instrument
facts were needed to find or fix either one — this was a document-consistency pass, not
further hardware research.

## Final scoring

| Area | Weight | Score | Weighted result |
|---|---:|---:|---:|
| Instrument grounding | 10% | 9.7 | 0.97 |
| Connection lifecycle | 10% | 9.6 | 0.96 |
| Command inventory vs. keyword coverage | 15% | 9.7 | 1.46 |
| Signal-integrity/safety requirements | 20% | 9.7 | 1.94 |
| Exception hierarchy | 10% | 9.7 | 0.97 |
| Testing | 15% | 9.7 | 1.46 |
| Packaging/versioning | 5% | 9.5 | 0.48 |
| Documentation/examples | 5% | 9.0 | 0.45 |
| Acceptance criteria/traceability | 5% | 9.6 | 0.48 |
| Document mechanics | 5% | 9.8 | 0.49 |

**Final task readiness score: 9.66/10.**

## Readiness decision

**APPROVED — READY TO START GATE 2 CODE WRITING.**

Six defects across two review passes were closed with concrete edits, not deferred with
caveats — this differs from `rf_tbs1000c`'s first readiness pass, which had to carry two
genuinely unresolvable-from-documentation items forward (GPIB confirmation, `*LRN?`
format). This instrument had no equivalent: `*LRN?` is fully documented in its own manual
entry, and GPIB/USB/LAN are all confirmed-standard rather than requiring an optional
adapter, so the architecture in §5.1 rests on solid ground already.

Three items remain in §19 as open questions (VISA backend coverage across all three
interfaces in the actual target environment, the exact overvoltage error text, and whether
LXI/mDNS discovery is in scope) — all three are hardware/environment facts no amount of
further document review or manual research would resolve, correctly deferred to Gate
2/hardware testing rather than guessed at. Documentation/examples is the one domain held at
9.0 rather than higher, deliberately: no README, MkDocs content, or example `.robot` files
exist yet at Gate 1 — that's expected at this stage, not a defect, but it keeps this domain
from claiming a score it hasn't earned.

Implementation may begin against this document as written.
