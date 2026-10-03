# Configured source readers

Continue ticket 21's full Company/Person/GLEIF equivalence and installed empty-store proof. This branch starts with the generic parallel-array iteration needed by raw SEC submissions. No reader is retired before equivalent behavior is verified.

- [x] Review engine and loader history with GoF; retain the existing function-based design — independent Standards review confirmed no refactor warranted; 2026-10-03 17:23 ET.
- [x] Add bounded parallel-array record iteration with explicit length handling and strict contract validation — 11 Rust acceptance cases passed; 2026-10-03 17:23 ET.
- [x] Verify alignment, optional arrays, empty input, malformed shapes, limits and deferred raw evidence — Rust acceptance and 7 Python tests passed in CI; 2026-10-03 17:23 ET.
- [x] Compare configured filing projections against the old loader on pinned captured data — 1,000 receipt-hash-verified filings, 107,197 rows, accession/form only; committed parallel-projection-qualification.json; 2026-10-03 17:23 ET.
- [x] Document the grammar and verify Python/installed-worker exposure — bundled READING.md and all three installed PG16 parse/master variants passed in Engine CI; 2026-10-03 17:23 ET.
- [x] Open a dependent PR; verify all CI suites and aggregate gate — PR #808, implementation run 37154609041: 1,461 Python and 36 Rust tests passed, zero skips, one existing xfail; Standards and Spec reviews found zero defects; 2026-10-03 17:23 ET.
- [ ] Company read block, scalar/classification/address/grouping equivalence, then reader/loaders retirement.
- [ ] Person read block and equivalence.
- [ ] GLEIF read block and all positive/failure equivalence, then reader retirement.
- [ ] Installed empty-store full proof: 6,414 Companies, 3,052 CIK+LEI, unchanged replay.

## Design review

Engine/loader history confirms parallel-array expansion is currently source-specific. Add one generic record-selection function, retaining existing expression evaluation and record checks. No new GoF class hierarchy is justified. Array alignment policies are explicit contract data, never inferred from a feed name.

## Qualification boundary

The captured-data comparison covers only accession_number and form. It does not establish all filing columns, Company classification, Name Census, Person, GLEIF, assertion identity or failure equivalence. All four remaining parts above stay incomplete; no legacy code or source Rules versions changed. CI uses real PostgreSQL 16 with distinct restricted worker and verifier roles.
