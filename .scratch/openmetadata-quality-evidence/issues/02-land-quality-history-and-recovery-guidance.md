# Land Per-Load Guidance and Work Map

Type: task
Status: claimed
Blocked by: none
Blocks: 07
Labels: wayfinder:task

## Question

Does the merged guidance in [Map and document per-load quality evidence (#1480)](https://github.com/paulananth/edgartools-platform/pull/1480), checked against [Restore verified per-load OpenMetadata quality results (#1484)](https://github.com/paulananth/edgartools-platform/pull/1484), accurately state per-load API readback and the manual recovery gate while distinguishing shipped code from the still-unmet recovery and verification work?

## Checklist

- [x] Confirm [Map and document per-load quality evidence (#1480)](https://github.com/paulananth/edgartools-platform/pull/1480) used exact head `bd0499e0dee363f119066ab5c01c2884851ff739` and merged as `e3918dcd74ef8ff11d26e501d8c5b3ccc1dccda6`; all 20 checks passed. Verified by `gh pr view 1480` and `gh pr checks 1480` (2026-11-07 15:44 ET).
- [x] Reconcile the legacy latest-only `--results FILE` description with the per-load `--bookkeeping-run` publisher and exact history readback contract. Both inputs use timestamp history readback; `--bookkeeping-run` wins when both flags are present. Verified against `edgar_warehouse/rules/cli.py` and `catalog.py` (2026-11-07 16:20 ET).
- [x] Clarify that the recovery switch is conditional and manual; keep owner, resume, measured recovery and maximum gates deferred to [Set and Prove the Recovery Maximum](04-set-and-prove-recovery-maximum.md). The load skill now points at that recovery section instead of restating a second gate. Verified against `silver_land.py` (2026-11-07 16:20 ET).
- [x] Add token lifecycle guidance that distinguishes short-lived login tokens from eight-day PATs and records the unsupported 2.0.2 API/CLI issuance boundary. Verified by reading `skills/openmetadata/references/TOKEN-LIFECYCLE.md` (2026-11-07 16:20 ET).
- [x] Review the final skill and map diffs and links. Standards and Spec reviews found two false contracts: legacy confirmation does not use a `testCaseResult` projection, and `--bookkeeping-run` wins over `--results`. Both are corrected. Documentation checks passed (101 tests, 2026-11-07 16:21 ET); overlap guard found no overlap. GoF review: no structural refactor is justified.
- [ ] Publish and merge the corrective follow-up PR after review and CI pass. Draft PR [Correct per-load quality guidance (#1496)](https://github.com/paulananth/edgartools-platform/pull/1496) is open at head `be26520b64b5d386f958b865c80126e0742f532f` (2026-11-07 16:23 ET). CI has not been confirmed and it is not merged.
- [ ] Record the follow-up head and merge result here; update the map and dependency edge.
- [ ] Learning → skill: record each skill/reference changed or `none`.
