# Retire custom ticker catalog parsing

Parent goal: self-sustaining installed Rules creator/parsing/MDM/custom orchestration and complete old-parser retirement. Base PR #826 e76fb929. Local qualification only.

- [x] Inventory retained callers/branches and GoF history; prove configuration gaps for dictionary entries, row selection, compact rank and permissive matrix layout. — 2026-10-05 07:58 ET; consumer inventory and git history inspected.
- [x] Express both ticker layouts and accepted/skipped/refused rows with generic bounded iteration, predicates and configuration; retain strict defaults. — 2026-10-05 07:58 ET; 78 focused Python and 87 Rust cases passed; strict defaults retained.
- [x] Compare exact typed output, compact rank and refusal decisions across a finite shape/value matrix with deliberate fault checks. — 2026-10-05 07:58 ET; 11,806 audit cases, zero differences; three deliberate faults detected.
- [x] Qualify pinned catalog bytes and verified Company joins using the replacement reader. — 2026-10-05 07:58 ET; both captured layouts: 10,391 rows each, five Company joins; 27.412s matrix, 20.690s dictionary; zero SEC requests.
- [x] Remove the unused runtime custom ticker parser after consumer inspection, retaining an independent historical oracle only for qualification. — 2026-10-05 07:58 ET; runtime consumer search empty; historical oracle moved to tests/support.
- [x] Verify installed bundle, full CI and independent Standards/Spec review; commit/push/create a reviewable PR. — 2026-10-05 08:06 ET; installed 2 passed/no skips in 112.26s; both reviews closed; PR #827; CI 37306744441 passed every suite and aggregate gate on 4cbbcc71. Final evidence commit must pass CI before readiness.
- [ ] Finish active submissions loader replacement, census/cascade/provenance, GLEIF/acquisition, full installed population/replay and complete parser retirement in the parent goal.

## Installed qualification

Both catalog modes passed from committed c756ce91 through the installed bundle, source worker and independent verifier with restricted PostgreSQL 16 roles: 2 passed, no skips, in 112.26 seconds. The exchange and dictionary contracts were loaded from the installed package.

Independent Standards/GoF and Spec reviews closed the scoped findings. The Spec report-layout issue was corrected by sharing the complete fields/data array predicate; the Standards numeric-header concern was withdrawn after checking ordered raw JSON parsing.

PR #827 remains draft until CI passes on this final evidence commit. PR #826 supplies the strict matrix reader and remains its open dependency. No merge, source activation or deployment is included.
