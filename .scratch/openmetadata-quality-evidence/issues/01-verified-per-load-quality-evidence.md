# Restore Verified Per-Load Quality Evidence

Type: task
Status: resolved
Origin: GitHub issue [Preserve verified per-load silver quality evidence](https://github.com/paulananth/edgartools-platform/issues/1434) and its approved plan
Blocked by: none
Labels: wayfinder:task

## Question

How should the implementation preserved on the closed PR **Preserve verified
per-load quality evidence for OpenMetadata** (#1479) be restored on a fresh
branch from current `main` and integrated without losing its tested behavior?

## Checklist

- [x] Capture version-2 silver quality outcomes in immutable, source-value-free work-unit receipts while retaining version-1 compatibility. Verified by `tests/unit/test_silver_land_quality.py` (5 passed, 2026-11-06 19:32 ET).
- [x] Recompute each receipt's checks and preserve flag versus exception counts. Verified by `tests/unit/test_silver_land_quality.py` (5 passed, 2026-11-06 19:32 ET).
- [x] Aggregate only verified work-unit receipts; keep incomplete evidence unknown and reject mismatched attempts or unsafe counts. Verified by `tests/unit/test_bookkeeping_quality.py` (5 passed, 2026-11-06 19:32 ET).
- [ ] ~~Prove attempt supersession between admission precheck and the atomic database completion boundary.~~ Deferred to [Prove Atomic Attempt Supersession](03-prove-atomic-attempt-supersession.md); the prior integration test could not import the compiled `source_contract` extension.
- [x] Publish every per-load result with stable Bookkeeping correlation, idempotent replay and exact assigned-timestamp API readback. A mismatching row gets at most one PATCH correction and must read back exactly; duplicate POST retries are not used. If work units share the same observed millisecond, deterministic adjacent API history keys preserve each row; the original observation time stays in result detail. Verified by focused tests (63 passed, 2026-11-06 21:55 ET) and a synthetic local API history write/read/delete probe. The local API rejected a duplicate POST and accepted repeated identical PATCH corrections.
- [x] Add a direct `rules catalog` path for completed Bookkeeping run evidence and preserve nonzero outcomes for unknown, drifted or failed publication. Verified by focused tests (63 passed, 2026-11-06 21:55 ET); incomplete runs expose verified units and mark missing results unknown without changing Bookkeeping state. The short status names run-level incompletion even if no units are unknown.
- [x] Qualify recovery readiness before enabling version-2 evidence: name an owner, document the resume procedure, prove a disposable resume, and set a measured maximum. Done in [Set and Prove the Recovery Maximum](04-set-and-prove-recovery-maximum.md): the platform operator owns recovery, the procedure is in `skills/bookkeeping/RECOVERY.md`, the disposable resume measured 0.146 s to 0.263 s over nine runs with no provider data, and the operator set the maximum at 5 minutes (2026-11-09 18:52 ET). The worker still checks `SILVER_QUALITY_EVIDENCE_V2` only when a frozen step requests `silver.quality.evidence.v2`; this manual opt-in does not verify the prerequisites, so the feature stays disabled pending the operator's enablement decision.
- [x] Confirm API history stores the exact synthetic load reference and confirm no `Shared` domain exists. Verified through the local OpenMetadata API; synthetic result was deleted, and the domain query returned false (2026-11-06 19:30 ET).
- [ ] ~~Observe in the shipped OpenMetadata UI that operators can find historical per-load results and distinguish confirmed, pending and failed publication.~~ Deferred to [Observe Per-Load History in the Shipped OpenMetadata UI](06-observe-history-in-shipped-openmetadata-ui.md); the repository requires operator observation of the shipped UI.
- [x] Write the Bookkeeping recovery and OpenMetadata result-history guidance in this separate change after PRs #1432 and #1418 were closed. Verified by reviewing both skill diffs (2026-11-06 20:32 ET).
- [x] Verify the installed data bundle imports the new Bookkeeping quality module without duplicating it across wheels. The first PR head failed `test_the_bundle_installs_whole_with_no_file_in_two_wheels` because the Bookkeeping wheel omitted `clean/quality.py`; the Bookkeeping wheel now includes it. Verified by the installed-bundle test passing in the Engine CI job for PR #1484 head `216e83dd` (2026-11-07 11:25 ET).
- [x] Run code review, resolve the misleading incomplete-run summary finding, and publish draft PR [Preserve verified per-load quality evidence for OpenMetadata (#1479)](https://github.com/paulananth/edgartools-platform/pull/1479); closed at the operator's request, with branch and commits retained. Verified by checking the GitHub PR record (state CLOSED, retained head `f683bbcc4eed4e1c90d2e78f8ff77a25aa63726c`) at 2026-11-07 15:28 ET.
- [x] Integrate the preserved implementation into a new PR from the fresh branch rebased onto current `origin/main` after PRs #1481–#1483 merged. PR [#1484](https://github.com/paulananth/edgartools-platform/pull/1484) passed every current-head CI check and merged as `8d41e29e` (2026-11-07 11:25 ET).
- [x] Add the recovery-format enablement gate to `skills/bookkeeping/RECOVERY.md` and the exact-timestamp history/readback contract to `skills/openmetadata/references/QUALITY-RESULT-HISTORY.md`. Verified by reviewing the document diff (2026-11-06 20:32 ET).
- [x] Learning → skill: `skills/bookkeeping/RECOVERY.md` → **Enable a new receipt format**; `skills/openmetadata/SKILL.md` points per-load history readers to `skills/openmetadata/references/QUALITY-RESULT-HISTORY.md`. Verified by reviewing the document diff (2026-11-06 20:32 ET).

## Answer

The implementation was restored in [Restore verified per-load OpenMetadata quality results](https://github.com/paulaananth/edgartools-platform/pull/1484), merged at `8d41e29e01ea30f462fd8612e25d08a5cf3f1033` from checked head `216e83ddd063a65589467074e6ce4a7150fea910`. All 12 reported checks pass on that head. The implementation-restoration question is complete.

The attempt-supersession proof and shipped-UI observation remain open in [Prove Atomic Attempt Supersession](03-prove-atomic-attempt-supersession.md) and [Observe Per-Load History in the Shipped OpenMetadata UI](06-observe-history-in-shipped-openmetadata-ui.md). The recovery-maximum work is resolved in [Set and Prove the Recovery Maximum](04-set-and-prove-recovery-maximum.md): the owner, procedure, measured resume and the operator's 5-minute maximum are recorded. These are separate gates, not blockers to this implementation task. Version-2 receipts remain disabled until the operator authorizes enablement.
