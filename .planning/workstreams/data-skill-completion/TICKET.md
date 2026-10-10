# Self-sustaining skills completion

User goal: one installable skill bundle containing the Rules creator and orchestration for parsing, MDM and custom parsing when configuration cannot express the operation. Continue the unfinished checklist from ticket 21; preserve the complete scope.

- [x] Audit all five gates and outstanding Company, Person, GLEIF and empty-store requirements — live files and PRs #805/#806; remaining items below; 2026-10-03 16:52 ET.
- [x] Demonstrate a real custom parsing gap against the existing engine primitives — date returns text and number returns null for an ISO instant; 21 focused tests passed; 2026-10-03 16:52 ET.
- [x] Draft one generic versioned function, tests and Mapping Document support; retain the code/rules approval boundary — no source rule references epoch_microseconds; PR #807; 2026-10-03 16:52 ET.
- [x] Prove custom parsing through an installed worker and independent verifier — both variants passed locally (165.57s); Engine CI: 32 Python and 25 Rust tests, zero skips; 2026-10-03 16:59 ET.
- [x] Open a dependent PR and verify CI; custom code remains inactive pending operator review — PR #807; run 37153276661 all six jobs passed; independent Standards and Spec reviews found zero defects; 2026-10-03 16:59 ET.
- [ ] Company read block and complete positive/failure equivalence before retiring its reader/loaders.
- [ ] Person read block and equivalence.
- [ ] GLEIF read block and complete equivalence before retiring its reader.
- [ ] Full installed-bundle empty-store proof: 6,414 Companies, 3,052 CIK+LEI, unchanged second pass.

## Audit

PR #805 merged: installed bundle, Rules creator and command/link drift checks. PR #806: verified worker parse → prepare → merge and independent publication. This paragraph described the initial audit. Current Company/Person/GLEIF read blocks exist; their complete runtime retirement and full installed population proof remain unfinished. Current continuation and corpus evidence are tracked in `.planning/workstreams/gleif-member-contracts/TICKET.md`. PRs #806/#807 are merged with all five suites and aggregate gate passed (live GitHub reverified 2026-10-06 21:40 ET).

## GoF review

Leave the function registry and worker adapter interfaces. A single versioned scalar conversion belongs in the existing registry. Mapping Document generation needs a small recursive traversal of its declared custom expressions, with no new class hierarchy.

## Remaining proof inputs located

- Frozen SEC population: `~/.local/share/edgartools/clean-mdm/captures/sec.submissions.company/all-76230/` (manifest and receipts present).
- Golden Copy: `~/.local/share/edgartools/clean-mdm/research/gleif-20260911-1600/01-20260911-1600-gleif-goldencopy-lei2-golden-copy.json.zip` (885 MiB).
- Existing census: `~/.local/share/edgartools/clean-mdm/proving/cm27/census.json` (5.5 MiB).
- Prior baseline: `.scratch/company-mastering/research/27/report.json`; harness `.scratch/company-mastering/research/27_proving_run.py`.

Hash validation on 2026-10-09 21:22 ET: the Golden Copy is 927,550,946 bytes and sha256 `1b6cd9cda3f94269fd406ee481842ea042b699e95eb5b8124b1496d4fda36a6a`. The Name Frequency file `proving/cm27/census.json` is 5,717,347 bytes, sha256 `84522f67c6d61c8ab115130ac96677320f5307a4f40dbf077a6693e59cec44cf`. The seven bundles hold 6,726 records. The prior harness uses the old readers directly and is not proof of installed configured-worker orchestration. No installed-bundle driver for this population exists. A current-policy checkout replay failed in 46.88 seconds on 2026-10-09 21:26 ET because it loaded the installed engine extension, which refuses a nested object field. Engine build ae627570 accepts that GLEIF mapping. A rerun on that build is process 26113, started 2026-10-09 21:32 ET.

## Review and failure evidence

Standards and Spec reviewers found no defects in the initial custom-trial code. CI and the first local installed run exposed shared Rules version identity between trial variants; the activated version correctly refused replacement evidence. Fixed with separate pipeline names and separate MDM databases. Repeat qualification is required.

Implementation CI: https://github.com/paulananth/edgartools-platform/actions/runs/37153276661. Final documentation push triggers another CI run. Overall goal remains incomplete because the four source/corpus requirements above are unchecked.
