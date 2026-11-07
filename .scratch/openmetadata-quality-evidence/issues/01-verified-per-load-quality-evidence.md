# Implement verified per-load quality evidence

Type: task
Status: claimed
Origin: GitHub issue #1434 and the approved plan in the issue-1434 plan worktree

## Checklist

- [x] Capture version-2 silver quality outcomes in immutable, source-value-free work-unit receipts while retaining version-1 compatibility. Verified by `tests/unit/test_silver_land_quality.py` (5 passed, 2026-11-06 19:32 ET).
- [x] Recompute each receipt's checks and preserve flag versus exception counts. Verified by `tests/unit/test_silver_land_quality.py` (5 passed, 2026-11-06 19:32 ET).
- [x] Aggregate only verified work-unit receipts; keep incomplete evidence unknown and reject mismatched attempts or unsafe counts. Verified by `tests/unit/test_bookkeeping_quality.py` (5 passed, 2026-11-06 19:32 ET).
- [ ] Prove attempt supersession between admission precheck and the atomic database completion boundary. Integration test added; blocked locally because the worktree cannot import the compiled `source_contract` extension.
- [x] Publish every per-load result with stable Bookkeeping correlation, idempotent replay and exact timestamped API readback. Verified by focused catalog tests (59 passed, 2026-11-06 19:32 ET) and a synthetic local API history write/read/delete probe.
- [x] Add a direct `rules catalog` path for completed Bookkeeping run evidence and preserve nonzero outcomes for unknown, drifted or failed publication. Verified by focused catalog tests (59 passed, 2026-11-06 19:32 ET).
- [x] Keep version-2 evidence disabled until the owner, resume, measured-recovery and maximum-time gates are met. Verified by the explicit `SILVER_QUALITY_EVIDENCE_V2` gate and its default-disabled unit test (5 passed, 2026-11-06 19:32 ET).
- [x] Confirm API history stores the exact synthetic load reference and confirm no `Shared` domain exists. Verified through the local OpenMetadata API; synthetic result was deleted, and the domain query returned false (2026-11-06 19:30 ET).
- [ ] Observe in the shipped OpenMetadata UI that operators can find historical per-load results and distinguish confirmed, pending and failed publication. Repository policy prohibits agent UI automation; operator observation remains required.
- [ ] Update Bookkeeping and OpenMetadata skill guidance after their overlapping draft PRs #1432 and #1418 merge. Data-operations skill updated here; overlap guard passes for the current branch.
- [ ] Run code review, resolve findings, commit and publish a draft PR. Mark ready only after remaining acceptance and integration gates pass.
- [ ] Learning → skill: keep the per-load operator flow and recovery-gate lesson in the appropriate shared skills; record the final line changed after remaining skill ownership is released.

## Next action

Complete the review and draft PR. Keep this ticket claimed and the PR draft while
the local PostgreSQL race proof, UI observation, and overlapping skill edits are
still open.
