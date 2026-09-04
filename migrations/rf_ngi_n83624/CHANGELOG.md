# Changelog

## Unreleased

- Fixed `final_status` being reported as `PASS` for every remaining evidence run at suite end regardless of recorded errors. `_finalize_remaining_evidence_runs` passed a fixed `status="PASS"` to every run it swept, so an alias whose only operation failed — a connection timeout, for example — was summarised as `PASS` with `error_count: 1`. Each alias is now judged on its own record via a new `EvidenceRun.has_errors` property. This is RFDS-008 §6.1 "no silent success": an operation that did not demonstrably succeed shall not be recorded as successful.

- Fixed evidence runs never being finalized when their alias never held a session. `_finalize_closed_sessions` only finalizes aliases that *lost* a session, but `_evidenced` creates a run for whatever alias a keyword resolves to — so any keyword called before `Open N83624 * Connection` (a query, or `Close All N83624 Connections` on an empty registry) left an evidence directory containing `environment.json` and `events/` but no `run_summary.json`, `evidence_manifest.json` or `integrity/checksums.sha256`: a permanently incomplete, unverifiable RFDS-008 record. `_end_suite`/`_close` now finalize every remaining run via `_finalize_remaining_evidence_runs`, unconditionally — `auto_close_on_suite_end` governs closing *connections*, never whether evidence is left complete on disk. This also completes evidence for sessions intentionally left open under `auto_close_on_suite_end=False`.

## v26.01 - 2026-07-18

- Added production-oriented Robot Framework library over the supplied NGI N83624 Python driver.
- Added named TCP, UDP, per-channel UDP, serial, and emulator sessions.
- Added explicit output arming, finite-limit validation, guarded raw SCPI, audit logging, assertions, heartbeat, and recovery keywords.
- Added best-effort all-channel shutdown that continues after individual channel failures.
- Fixed heartbeat-close lock ordering and monotonic communication timestamps in the inherited core.
- Added 14 examples, runners, tests, task/readiness documents, review documents, GitHub Actions, GitHub Pages, and setup/HIL guides.
