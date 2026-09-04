# Task Readiness Review: `rf_agilent34411a` Driver Task Document

Reviewed document: `ROBOT_FRAMEWORK_DRIVER_TASK_v26.01.md`. This is a readiness review
of the *task document itself* (is it specific, internally consistent, and grounded
enough to implement against without guessing) — not RFDS-010, which governs
release-readiness of shipped code, and does not apply to a pre-code planning artifact.
Same methodology used for `rf_tbs1000c` and `rf_agilent33220a`'s task readiness
reviews: weighted domain scoring, corrections applied, final score, decision.

## Initial assessment

| Domain | Weight | Score (0–10) | Notes |
|---|---:|---:|---|
| Grounding in real hardware facts | 25% | 6 | §2 was well-sourced but carried 6 open questions, 3 of which blocked whole keyword groups (§9 temperature units, §10 data logging, §11 state storage) from being implementable without guessing. |
| Internal consistency | 20% | 6 | Numbering bug: 4 places referenced "§21" for the open-questions section, which is actually §19 (only 19 sections exist). A maintainer following one of those cross-references would land on the wrong (nonexistent) section. |
| Keyword/test coverage completeness | 20% | 8 | §8–§12 keyword groups were complete for what was confirmed, but §9 was missing `TRIGger:COUNt` (the outer trigger-event count, distinct from `SAMPle:COUNt`) and `SAMPle:SOURce`/`SAMPle:TIMer` entirely — a real gap, not just an open question. |
| Safety/signal-integrity coverage | 15% | 8 | §6 correctly captured the physical protection limits, front/rear switch, calibration exclusion, overload handling, and the `CALCulate:FUNCtion NULL` deprecation trap. Missing: no guard against the instrument being left in `34401A`/`34410A` SCPI-language-emulation mode (`SYSTem:LANguage`), which would silently break most of this driver's command surface. |
| Precedent reuse (vs. reinventing patterns already proven in this repo) | 20% | 9 | Correctly pointed to `rf_agilent33220a`'s `_ScpiEnum`, `_dispatch_concatenated`/`explicit_root`, `_robot_value`, multi-alias session shape, and "reject-before-`*RCL`" pattern rather than re-deriving any of them. |

**Weighted initial score: 7.15/10.**

## Corrections applied

1. **Resolved 4 of 6 open questions by finding the actual Programmer's Reference-
   equivalent document.** The User's Guide alone repeatedly deferred to a separate
   *Agilent 34410A/11A/L4411A Programmer's Reference Help* that wasn't initially
   available. A web search turned up the *Agilent 34410A/11A Command Quick Reference*
   (Agilent Technologies, Jan 2006) — a complete SCPI syntax listing for the whole
   command set. Read in full and cross-checked against every claim already in the task
   doc (nothing it confirmed contradicted what was already written). This resolved:
   - Temperature units: `UNIT:TEMPerature {C|F|K}` — confirmed exactly as the earlier
     "reasonable guess."
   - `MEMory:` state-storage subsystem — confirmed in full:
     `*SAV`/`*RCL {0|1|2|3|4}`, `MEMory:NSTates?`, `MEMory:STATe:CATalog?`,
     `:DELete`/`:DELete:ALL`, `:NAME`/`:NAME?`, `:RECall:AUTO`, `:RECall:SELect`,
     `:VALid?`. §11 rewritten from "must confirm before implementing" to a complete,
     confirmed keyword list.
   - Remote-driven data logging: no dedicated "start logging" command exists: the
     confirmed mechanism is `DATA:COPY NVMEM, RDG_STORE` (persist the current volatile
     reading batch into non-volatile memory), plus `DATA:LAST?`, `DATA:POINts?`,
     `DATA:REMove?` for the volatile side. §10 rewritten accordingly, and marked
     "scope is final" rather than "keywords deferred."
   - `CONFigure`/`MEASure?` parameterized syntax — confirmed as
     `[{<range>|AUTO|MIN|MAX|DEF} [,{<resolution>|MIN|MAX|DEF}]]` for every function.
2. **Added the two keyword gaps found while cross-checking the Quick Reference against
   §9:** `TRIGger:COUNt` and `SAMPle:SOURce`/`SAMPle:TIMer`, with a short explanation
   of why the trigger-count/sample-count distinction matters (total readings = the
   product of the two, the standard SCPI trigger model) so a future reader doesn't
   need to re-derive it.
3. **Added §6 item 7 (`SYSTem:LANguage` guard)** — a genuinely new safety-relevant
   finding surfaced only by reading the Quick Reference's `System-Related Commands`
   section, which the User's Guide excerpts read during Gate 1 never mentioned. Wired
   into `Check Communication`/`Connect` per the description, and into the hardware
   test plan (§14.3).
4. **Fixed the `§21` → `§19` numbering bug** in all 4 locations (lines that survived
   from the original draft plus 2 introduced while writing the corrections above —
   caught by grepping the whole file for `§21` after finishing the content edits, not
   just the lines touched in this pass).
5. **Narrowed §19 (open questions) from 6 items to 2**, both explicitly marked
   low-priority and non-blocking for Gate 2 as scoped (AC/frequency numeric ranges —
   not needed since §8 doesn't client-side-validate those ranges; the residual
   `CONFigure`/`MEASure?` nuance — not needed since this driver doesn't use that
   command family at all). Acceptance criteria (§18) updated to match: the old
   "instrument memory storage implemented only if §21 item 3 resolved" conditional
   is gone, since it's now unconditionally in scope.

## Final scoring

| Domain | Weight | Score (0–10) |
|---|---:|---:|
| Grounding in real hardware facts | 25% | 9.5 |
| Internal consistency | 20% | 10 |
| Keyword/test coverage completeness | 20% | 9.5 |
| Safety/signal-integrity coverage | 15% | 9.5 |
| Precedent reuse | 20% | 9 |

**Weighted final score: 9.53/10.**

Remaining 0.47 deduction: the two genuinely open items in §19 are real gaps, not
resolved — they're just correctly scoped as non-blocking rather than something to
paper over. A document that claimed zero open questions after this pass would be
overclaiming.

## Readiness decision

**Ready to proceed to Gate 2 core implementation.** Every keyword this task document
commits to for Gate 2 is now backed by a confirmed SCPI mnemonic from at least one of
the two source documents read directly (User's Guide, Command Quick Reference); no
keyword in §7–§12 ships against a guessed command shape. The two remaining open
questions in §19 are correctly scoped as non-blocking and don't gate any keyword this
task actually implements.
