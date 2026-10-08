# Codex handoff X1, X2, X3 and J1

Operator assignment, 2026-10-08: "Codex: X1 (putting the pin beside the inline place rows in source.yaml), X2, X3, and writing your J1 words on the Company merge-rule ticket."

- [x] X1: add the published place pin beside inline rows; preserve lookup behavior, synchronize the census reading copy and inspect live digest consumers. Verified by live merged artifacts and verification.json (2026-10-08 06:44 ET); X1 landing awaits the separate merge checkbox.
- [x] X2: reconcile only the two stale GLEIF runtime completion lines against all six authenticated reports. Verified against live gh merges and authenticated saved reports (2026-10-08 06:44 ET).
- [x] X3: reconcile cited merged PRs clause by clause; preserve incomplete retirement/population checkboxes. Verified against live gh merges and authenticated saved reports (2026-10-08 06:44 ET).
- [x] J1: record the operator's decision on the Company name-rule ticket; verify agreement with Claude's merged decision. Verified against live gh merges and authenticated saved reports (2026-10-08 06:44 ET).
- [ ] Verify affected contracts and tests, inspect the final diff, run the overlap guard, commit and create a reviewable PR.
- [ ] Merge X1 only after the operator's merge instruction; this handoff does not complete parser retirement.

Current main is 862a1e66. C3 already merged as #862 (4840c6ba): quality reads the published pin and the old reference YAML is gone. Do not restore that retired YAML to meet the handoff's older snapshot conditions.

GoF/history review: reference.rs remains a bounded frozen-table interpreter. Source mapping history changed for Company reading and configured field projection (#821, #828, #858). Adding provenance metadata needs no reader refactor or pattern hierarchy. Existing reference lookup and rows remain byte-for-byte intact.

Verification: 677 affected Company/reference/census/MDM tests passed in 66.39s. `verification.json` records both source file/document digests, exact inline-row and lookup equivalence, unchanged MDM mapping and all six authenticated report hashes. The repository contains four historical proofs of the old source bytes; those stay frozen. No live Rules registry, frozen run or deployment was inspected or changed.

Independent review: Spec found no scoped blocker. Standards/GoF found one evidence-scope wording issue; corrected `verification.json` and this ticket to say repository-only digest search, with external stores explicitly uninspected. No runtime refactor recommended.
