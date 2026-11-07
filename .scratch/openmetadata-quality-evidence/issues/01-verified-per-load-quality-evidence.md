# Restore Verified Per-Load Quality Evidence

Type: task
Status: open
Origin: GitHub issue [Preserve verified per-load silver quality evidence](https://github.com/paulananth/edgartools-platform/issues/1434) and its approved plan
Blocked by: none
Blocks: 03, 04, 05, 07
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
- [x] Publish every per-load result with stable Bookkeeping correlation, idempotent replay and exact timestamped API readback. A mismatching row gets at most one PATCH correction and must read back exactly; duplicate POST retries are not used. Verified by focused tests (62 passed, 2026-11-06 19:45 ET) and a synthetic local API history write/read/delete probe. The local API rejected a duplicate POST and accepted repeated identical PATCH corrections.
- [x] Add a direct `rules catalog` path for completed Bookkeeping run evidence and preserve nonzero outcomes for unknown, drifted or failed publication. Verified by focused tests (63 passed, 2026-11-06 19:49 ET); incomplete runs expose verified units and mark missing results unknown without changing Bookkeeping state. The short status names run-level incompletion even if no units are unknown.
- [x] Keep version-2 evidence disabled until the owner, resume, measured-recovery and maximum-time gates are met. Verified by the explicit `SILVER_QUALITY_EVIDENCE_V2` gate and its default-disabled unit test (5 passed, 2026-11-06 19:32 ET).
- [x] Confirm API history stores the exact synthetic load reference and confirm no `Shared` domain exists. Verified through the local OpenMetadata API; synthetic result was deleted, and the domain query returned false (2026-11-06 19:30 ET).
- [ ] ~~Observe in the shipped OpenMetadata UI that operators can find historical per-load results and distinguish confirmed, pending and failed publication.~~ Deferred to [Observe Per-Load History in the Shipped OpenMetadata UI](06-observe-history-in-shipped-openmetadata-ui.md); the repository requires operator observation of the shipped UI.
- [x] Write the Bookkeeping recovery and OpenMetadata result-history guidance in this separate change after PRs #1432 and #1418 were closed. Verified by reviewing both skill diffs (2026-11-06 20:32 ET).
- [x] Run code review, resolve the misleading incomplete-run summary finding, and publish draft PR [Preserve verified per-load quality evidence for OpenMetadata (#1479)](https://github.com/paulananth/edgartools-platform/pull/1479); closed at the operator's request, with branch and commits retained.
- [ ] Integrate the preserved implementation into a new PR; [Preserve verified per-load quality evidence for OpenMetadata (#1479)](https://github.com/paulananth/edgartools-platform/pull/1479) is closed and not merged.
- [x] Add the recovery-format enablement gate to `skills/bookkeeping/RECOVERY.md` and the exact-timestamp history/readback contract to `skills/openmetadata/references/QUALITY-RESULT-HISTORY.md`. Verified by reviewing the document diff (2026-11-06 20:32 ET).
- [x] Learning → skill: `skills/bookkeeping/RECOVERY.md` → **Enable a new receipt format**; `skills/openmetadata/SKILL.md` points per-load history readers to `skills/openmetadata/references/QUALITY-RESULT-HISTORY.md`. Verified by reviewing the document diff (2026-11-06 20:32 ET).

## Next action

Keep this ticket open. The original implementation PR is closed and its branch
is preserved. Restore that work through a fresh PR; the linked race-proof and
operator-observation tickets keep those acceptance gates distinct.
