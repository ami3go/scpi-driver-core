# Task Readiness Review

**Reviewed task:** Robot Framework driver for Tektronix TBS1000C
**Reviewed revision:** 26.01-draft
**Review date:** 2026-08-01

## Initial task assessment

The first drafted version covered the connection lifecycle, channel/trigger/acquisition
keywords, waveform decoding, and measurement-integrity requirements in solid, manual-grounded
detail — every command cited (`ACQuire:...`, `CH<x>:...`, `TRIGger:A:...`, `WFMOutpre?`, the
full `MEASUrement:IMMed:TYPe` enumeration) was pulled from the real Tektronix TBS1000C
Programmer Manual (077-1691-02) rather than assumed, and the RFDS-002 canonical connection
keywords were correctly specified as the primary API from the start instead of being bolted
on later, as happened with six of the eight existing packages in this repository.

It did not yet cover evidence-capture or configuration-portability workflows at all, and one
command group the driver silently depends on was missing from its own inventory.

| Area | Initial score | Main gap |
|---|---:|---|
| Instrument grounding | 9.5 | — |
| Connection lifecycle | 9.5 | — |
| Channel/trigger/acquisition keywords | 8.5 | No channel-naming keyword |
| Measurement integrity | 9.0 | — |
| Evidence capture (image/CSV/setup) | 0.0 | Not specified at all |
| Command inventory completeness | 7.0 | Event-status/error-queue commands used but not inventoried |
| Testing | 7.5 | No coverage for the (then-absent) evidence-capture features |
| Packaging/versioning | 9.5 | — |
| Documentation/examples | 9.0 | — |
| Acceptance criteria/traceability | 8.0 | Checklist didn't cover evidence-capture features |

**Initial readiness score: 7.2/10 — solid architectural foundation, but not ready to hand to
Gate 2 implementation: an entire required capability area (save image/CSV/setup) was
undefined, and every driver-level keyword needs backing commands actually inventoried before
implementation starts from this document alone.**

## Corrections applied

1. Added §10.1 `Save Screen Image`, grounded in `SAVe:IMAge`/`SAVe:IMAge:FILEFormat`/
   `SAVe:IMAge:LAYout`, correctly identifying that these write to the *instrument's* own
   filesystem and specifying the two-step `SAVe:IMAge` → `FILESystem:READFile` → host-file
   mechanism required to actually get the image onto the machine running Robot Framework.
2. Added §10.2 `Save Waveform To CSV`, built as a host-side decode of the already-specified
   `Get Waveform` path (no instrument-storage dependency, works against the simulator) with
   an optional vendor-native alternate (`SAVe:WAVEform:FILEFormat SPREADSheet`) documented
   for cross-checking rather than as the primary mechanism.
3. Added §10.3 `Save Setup`/`Restore Setup`, built around `*LRN?` as the primary host-file
   mechanism, with the vendor-native numbered-memory-slot alternate (`*SAV`/`*RCL`) and
   `RECAll:SETUp FACtory` documented alongside it. Flagged — rather than assumed — that this
   manual's own `*LRN?` entry doesn't document its return format, and specified a fallback
   mechanism and an explicit Gate 2 characterization step (§13.3, open question 5) instead
   of building on an unverified assumption.
4. Added a shared design constraint (§5.2) requiring one driver-layer file-transfer helper
   behind all three save-to-instrument-then-read-back keywords, rather than three
   independent implementations of the same two-step protocol sequence.
5. Added `Set/Get Channel Name` (§8), grounded in `CH<x>:LABel`'s actual 30-character limit
   and empty-string-clears behavior from the manual, with an explicit host-side validation
   requirement (reject before sending, don't let the instrument silently truncate).
6. Extended the simulator requirements (§12) to back all four new keywords offline: an
   in-memory instrument filesystem for the save/read-back mechanism, and a deterministic
   `*LRN?` response — so none of this capability area depends on real hardware to test.
7. Extended §13.1–§13.3 with concrete test cases for all four additions, including a
   corrupted-setup-file rejection test (§13.1 item 13) that wasn't implied by any earlier
   requirement.
8. Extended the §17 acceptance checklist with explicit, checkable criteria for the
   evidence-capture and channel-naming features instead of leaving them implicit in the
   general "keywords exist" line.
9. **(This review)** Added `*ESR?`/`*ESE`/`EVENT?`/`EVMsg?`/`ALLEv?` to §2's command
   inventory. `Check Communication` and the `Restore Setup` verification step both depend on
   reading the instrument's event-status queue, but no event-status command had been
   inventoried anywhere in the document — an implementer following §2 alone would not have
   known these commands existed. This is a real completeness gap the earlier pass through
   this document didn't catch on its own; verified against the manual (`*ESR?`, `EVENT?`,
   `EVMsg?`, `ALLEv?`, `*ESE` are all real, cross-referenced together in the source PDF)
   before adding it.

## Known residual gap (not corrected, judged acceptable for Gate 1)

- §7–§10 specify keyword behavior as `Set/Get Channel Scale`-style pairs rather than as two
  fully separate literal bullets the way §9's measurement-type enumeration or `rf_ngi_n83624`'s
  task document do throughout. The pattern is unambiguous and consistently applied, and every
  place where literal precision actually mattered (character limits, enum values, exact
  signatures for the RFDS-002 keywords) already has it. Expanding every pair into two bullets
  would add volume without adding information. Acceptable for a Gate 1 document; the
  `ai/ai_contract.yaml` authored at Gate 4 is the artifact that must carry exact per-keyword
  signatures, not this task document.
- §3 lists a `config/` directory (RFDS-014) but no section defines its schema content. None
  of the four capabilities addressed by this review cycle need it (they're all keyword
  arguments and file I/O, not persisted device-configuration profiles), so it's left as a
  Gate 2 item rather than force-fit into this pass.

## Second review pass — closing the carried-open items

The first pass ended "approved with two carried open items": GPIB scope-out and `*LRN?`'s
response format, both flagged as needing real hardware to resolve. Before accepting that as
final, this pass went back to primary sources rather than leaving them as permanent
unknowns:

1. **GPIB — resolved, not deferred.** Fetched the official TBS1000C Series datasheet
   (tek.com). It states plainly: no built-in Ethernet/RS-232, and GPIB only via the optional
   TEK-USB-488 converter on the rear USB device port. The programmer manual's interface
   table (`GPIB=Yes`) was describing what's reachable with that adapter, not a native port —
   this fully explains the earlier ambiguity instead of just working around it. §2 and §5.1
   updated; open question 1 struck through with the resolution, not left open.
2. **`*LRN?` — resolved, not deferred.** Re-examined the manual's own text more carefully
   and found `SET?`, a fully-documented command the manual states is identical to `*LRN?` —
   the earlier pass's PDF extraction had rendered `*LRN?`'s cross-reference to `SET?` as an
   unhelpful "This is identical to the query," without following that pointer. `SET?`'s own
   entry has a complete description, a real example response, and documents the exact
   `HEADer`/`VERBose` interaction that matters for parsing it. §2 and §10.3 rewritten from
   "characterize before implementing" to a fully specified design; §18 open question 5
   struck through.
3. **`config/` (RFDS-014) — closed, not carried.** The first pass judged this acceptable to
   defer since none of the reviewed features needed it. On reflection, an implementer
   starting Gate 2 from this document would still hit an undefined `config/` directory
   listed in §3 with nothing else about it — that's still a real gap for someone trying to
   start writing code today, even if none of the *specific* features already reviewed force
   it. Added §5.3 with a minimal, honestly-scoped schema (connection defaults, default image
   format, optional channel-label defaults) rather than force-fitting device-configuration
   language that doesn't apply to this instrument.

One item from the original §18 list is *not* resolved and cannot be from documentation
alone: exact model selection (TBS1052C vs. TBS1072C vs. ...) is a bench-inventory decision,
not a research question. USBTMC per-OS driver setup instructions remain a Gate 4
documentation-writing task, not a design blocker — nothing about §7–§13's keyword design
depends on which USBTMC backend a given lab ends up using.

## Final scoring

| Area | Weight | Score | Weighted result |
|---|---:|---:|---:|
| Instrument grounding | 10% | 9.8 | 0.98 |
| Connection lifecycle | 10% | 9.7 | 0.97 |
| Channel/trigger/acquisition keywords | 10% | 9.5 | 0.95 |
| Measurement integrity | 15% | 9.5 | 1.43 |
| Evidence capture (image/CSV/setup) | 20% | 9.7 | 1.94 |
| Command inventory completeness | 10% | 9.7 | 0.97 |
| Testing | 10% | 9.4 | 0.94 |
| Configuration profile (RFDS-014) | 5% | 9.3 | 0.47 |
| Documentation/examples | 5% | 9.2 | 0.46 |
| Acceptance criteria/traceability | 5% | 9.5 | 0.48 |

**Final task readiness score: 9.59/10.**

## Readiness decision

**APPROVED — READY TO START GATE 2 CODE WRITING.**

Both items the first pass carried forward as open are now resolved from primary sources
(the official datasheet and the manual's own `SET?` entry), not assumed away — §2, §5.1,
§5.3, §10.3, and §18 all reflect the resolution with citations back to where the evidence
came from. The `config/` gap identified as acceptable-but-present is now closed.

What remains open (§18: exact model selection, per-OS USBTMC driver docs) is ordinary,
expected Gate 2/4 work — a bench-inventory decision and a documentation-writing task — not
unresolved design questions. Nothing in §5–§13 depends on either being settled first.

The only genuine residual risk is the ordinary kind every hardware driver in this repository
carries: documentation can be wrong or firmware-version-dependent, which is exactly why
§13.3's hardware conformance suite exists and why every acceptance-criteria checkbox for
real-hardware qualification stays unchecked until it runs against a physical unit. That is
qualification risk, not task-readiness risk, and this document does not confuse the two
anywhere in its acceptance criteria (§17).

Implementation may begin against this document as written.
