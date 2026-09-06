# Task Readiness Review: `rf_ea_ps9000t` Driver Task Document

Reviewed document: `ROBOT_FRAMEWORK_DRIVER_TASK_v26.01.md`. This is a readiness review of
the *task document itself* — not RFDS-010, which governs release-readiness of shipped
code and does not apply to a pre-code planning artifact. Same methodology as the three
prior task readiness reviews in this repository: weighted domain scoring, corrections
applied, final score, decision.

## Initial assessment

| Domain | Weight | Score (0–10) | Notes |
|---|---:|---:|---|
| Grounding in real hardware facts | 25% | 9 | Every command and every "this feature is absent" claim was checked against the source's own per-series compatibility table for the PST column specifically — a materially stronger evidence trail than the three prior task docs, none of which had a multi-series compatibility matrix to check against. Only one genuinely open item (default IP transcription), and it's flagged as non-blocking rather than silently assumed. |
| Internal consistency | 20% | 6 | Same class of bug as the `rf_agilent34411a` task doc: 2 stray `§21` cross-references where the actual section is `§17` (this document only has 17 sections, not 19 or 21 — a template habit carried over from the two 19-section prior docs). Caught by the same grep-based numbering check that fixed the prior doc's version of this bug. |
| Keyword/test coverage completeness | 20% | 9 | §7–§10's keyword groups are complete for what's confirmed present, and — unusually for this repository's task docs so far — explicitly enumerate what's *excluded* and why (sink mode, resistance mode, supervision features, master-slave, function/sequence generator, MPP tracking, PV simulation, battery test, presets/recall), each traced to a specific compatibility-table finding rather than a generic "not implemented" note. |
| Safety/signal-integrity coverage | 15% | 9.5 | §6 identifies a genuinely new safety-relevant pattern not seen in the three prior drivers: this instrument requires *explicit* remote-control acquisition that can be *refused*, and the refusal surfaces asynchronously (on the next command, not the lock request itself) per the source document's own "errors are never returned automatically" rule. The task doc correctly derives that `Connect` must query `SYSTem:LOCK:OWNer?` after requesting the lock rather than trusting the write succeeded — this is not something the other three drivers needed to handle and was not copied mechanically from them. |
| Precedent reuse (vs. reinventing patterns already proven in this repo) | 20% | 9 | Correctly reuses the `_ScpiEnum` pattern, the "no concatenated-command replay needed" simplification from `rf_agilent34411a` (same reasoning: no `*LRN?`-equivalent exists here either), and the multi-alias session shape — while correctly declining to reuse `rf_agilent33220a`/`rf_agilent34411a`'s save/restore-setup keyword pattern, since this hardware genuinely lacks the underlying feature (confirmed via compatibility table, not assumed). |

**Weighted initial score: 8.35/10.**

## Corrections applied

1. **Fixed the `§21` → `§17` numbering bug** in both locations (§2's default-IP note, and
   §12.3's hardware-test-plan cross-reference), found via the same `grep -oE "§[0-9]+"`
   sweep that was added to this repository's process after catching the identical bug
   class in the `rf_agilent34411a` task doc — this is now a standard check before
   finalizing any task document in this repository, not a one-off fix.
2. No other corrections were needed on this pass. The research itself (§2) was thorough
   enough on the first attempt — grounded in a document with an unusually strong internal
   evidence structure (per-series compatibility tables covering ~13 device series) — that
   no keyword had to be walked back or newly discovered after the fact, unlike the
   `rf_agilent34411a` review, which needed a second research pass (finding the Command
   Quick Reference) to resolve several genuinely blocking open questions. Here, the single
   remaining open question (§17 item 1, the `198.168.0.2` vs. `192.168.0.2` default-IP
   transcription) does not block any keyword, since this driver never hardcodes a
   resource string (RFDS-002 always takes it from the caller) — it only affects the
   accuracy of a documentation note in the eventual README.

## Final scoring

| Domain | Weight | Score (0–10) |
|---|---:|---:|
| Grounding in real hardware facts | 25% | 9.5 |
| Internal consistency | 20% | 10 |
| Keyword/test coverage completeness | 20% | 9 |
| Safety/signal-integrity coverage | 15% | 9.5 |
| Precedent reuse | 20% | 9 |

**Weighted final score: 9.43/10.**

Remaining deduction: keyword/test coverage completeness is held at 9 rather than higher
because several device-configuration commands confirmed *present* for PST (LAN
configuration, analog-interface reference/REM-SB settings) were deliberately excluded
from the Gate 2 keyword surface as a scope judgment call (§2/§9) rather than a hardware
limitation — a reasonable call consistent with this repository's precedent, but a
judgment call nonetheless, not a fact-driven exclusion like the others.

## Readiness decision

**Ready to proceed to Gate 2 core implementation.** Every keyword this task document
commits to for Gate 2 is backed by a confirmed SCPI command from the source's own
per-series compatibility table; every excluded feature is backed by the same table
showing it absent for this series, not by a research gap. The one remaining open question
(§17) is confirmed non-blocking — it affects documentation accuracy, not any keyword's
implementability.
