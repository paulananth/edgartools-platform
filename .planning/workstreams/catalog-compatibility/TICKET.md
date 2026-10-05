# Retire custom ticker catalog parsing

Parent goal: self-sustaining installed Rules creator/parsing/MDM/custom orchestration and complete old-parser retirement. Base PR #826 e76fb929. Local qualification only.

- [x] Inventory retained callers/branches and GoF history; prove configuration gaps for dictionary entries, row selection, compact rank and permissive matrix layout. — 2026-10-05 07:58 ET; consumer inventory and git history inspected.
- [x] Express both ticker layouts and accepted/skipped/refused rows with generic bounded iteration, predicates and configuration; retain strict defaults. — 2026-10-05 07:58 ET; 78 focused Python and 87 Rust cases passed; strict defaults retained.
- [x] Compare exact typed output, compact rank and refusal decisions across a finite shape/value matrix with deliberate fault checks. — 2026-10-05 07:58 ET; 11,806 audit cases, zero differences; three deliberate faults detected.
- [x] Qualify pinned catalog bytes and verified Company joins using the replacement reader. — 2026-10-05 07:58 ET; both captured layouts: 10,391 rows each, five Company joins; 27.412s matrix, 20.690s dictionary; zero SEC requests.
- [x] Remove the unused runtime custom ticker parser after consumer inspection, retaining an independent historical oracle only for qualification. — 2026-10-05 07:58 ET; runtime consumer search empty; historical oracle moved to tests/support.
- [ ] Verify installed bundle, full CI and independent Standards/Spec review; commit/push/create a reviewable PR.
- [ ] Finish active submissions loader replacement, census/cascade/provenance, GLEIF/acquisition, full installed population/replay and complete parser retirement in the parent goal.
