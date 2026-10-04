# Configured Company main-document preparation

Parent goal stays self-sustaining installed Rules creator/orchestration and complete old-parser retirement. Base main 7730b68b. Local qualification only.

- [x] Inspect live callers, source contract, retained field/address/filing behavior and GoF history — SilverLandingStore and Company CLI still call retained loaders/preparation; source history and generic composition reviewed; 2026-10-04 18:42 ET.
- [x] Add an executable Company read block using existing generic primitives — 54 affected Python cases passed; exact raw Company types, full filing contract and address interpretation preserved; 2026-10-04 18:42 ET.
- [x] Prove actual read → combine → prepare receipts and retained field/address/form parity — immutable batch bytes, repeated combination and wrong-context refusal; 3 deliberate nested bool/int/float substitutions fail the strict comparator; 2026-10-04 18:42 ET.
- [x] Compare receipt-pinned captured documents with exact runtime evidence — qualification.json: 1,000 main captures, 1,000 Company rows and 107,197 filing rows, exact typed JSON matches across all three tables in 117.787 seconds; 500 independently verified source.read units; 2026-10-04 18:42 ET.
- [x] Verify affected tests, independent Standards/Spec review and all CI suites — 54 affected cases, both installed trials, both reviews closed; CI 37240926635 passed every suite and aggregate gate (1,704 Python, 77 Rust, one existing xfail, no skips). Final evidence commit also requires CI before readiness; 2026-10-04 18:44 ET.
- [x] Commit/push/create a reviewable PR with exact qualification scope — PR #821, no activation/deployment; evidence committed with this checklist; 2026-10-04 18:42 ET.
- [ ] Finish census/ticker/pagination provenance, GLEIF streaming, acquisition, adapter replacement, full installed population/replay and delete every old parser in the parent goal.

GoF: existing source.read/source.combine worker functions and native expression traversal already support this composition. Source history shows governance and producer additions; a new source-specific worker or class hierarchy is unnecessary. Retained readers remain comparison oracles until complete source equivalence is established.

## Installed and review evidence

Both installed trials passed with restricted PostgreSQL 16 worker/verifier roles: original 13F and Company main-source reading, 2 passed/no skips in 141.21 seconds at bdc2e426 (production read block unchanged by later strict-comparator correction). The Company source contract was read from the installed bundle and Bookkeeping finalized verified work.

Independent Standards/GoF and Spec reviewers found one comparator evidence gap: Python equality conflates booleans, integers and floats. Fixed at 21ac31f9 using canonical JSON digests, with three deliberate-fault regressions; both reviewers confirmed closure and no remaining scoped blockers.

## Active retirement callers

- `silver_landing_store.py`: imports/calls stage_company_loader, stage_address_loader and stage_recent_filing_loader from bronze_submission_extractors.
- `mdm/clean/cli.py`: calls prepare_company_bundle and write_name_census.
- `mdm/clean/name_census.py`: imports retained GLEIF inspect_archive.
- `mdm/clean/source_publications.py`: imports retained GLEIF validate_release/inspect_archive.
- `mdm/clean/native_consumption.py`: imports retained GLEIF record_evidence.

These live callers contradict complete retirement. The configured main read block supplies raw Company/filing/address tables; it does not establish census/cascade, catalog, paginated history, producer provenance or universal malformed-input equivalence. The final parent item stays unchecked.
