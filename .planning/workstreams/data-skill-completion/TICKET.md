# Self-sustaining skills completion

User goal: one installable skill bundle containing the Rules creator and orchestration for parsing, MDM and custom parsing when configuration cannot express the operation. Continue the unfinished checklist from ticket 21; preserve the complete scope.

- [x] Audit all five gates and outstanding Company, Person, GLEIF and empty-store requirements — live files and PRs #805/#806; remaining items below; 2026-10-03 16:52 ET.
- [x] Demonstrate a real custom parsing gap against the existing engine primitives — date returns text and number returns null for an ISO instant; 21 focused tests passed; 2026-10-03 16:52 ET.
- [x] Draft one generic versioned function, tests and Mapping Document support; retain the code/rules approval boundary — no source rule references epoch_microseconds; PR #807; 2026-10-03 16:52 ET.
- [ ] Prove custom parsing through an installed worker and independent verifier.
- [ ] Open a dependent PR and verify CI; custom code remains inactive pending operator review.
- [ ] Company read block and complete positive/failure equivalence before retiring its reader/loaders.
- [ ] Person read block and equivalence.
- [ ] GLEIF read block and complete equivalence before retiring its reader.
- [ ] Full installed-bundle empty-store proof: 6,414 Companies, 3,052 CIK+LEI, unchanged second pass.

## Audit

PR #805 merged: installed bundle, Rules creator and command/link drift checks. PR #806: verified worker parse → prepare → merge and independent publication. The source-specific read blocks and full-corpus proof remain absent. G4 has only callback rejection/failure tests before this follow-up.

## GoF review

Leave the function registry and worker adapter interfaces. A single versioned scalar conversion belongs in the existing registry. Mapping Document generation needs a small recursive traversal of its declared custom expressions, with no new class hierarchy.
