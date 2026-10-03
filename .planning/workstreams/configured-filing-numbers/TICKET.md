# Configured filing numbers

Continue ticket 21 and the filing column checklist. Complete source outputs and failure behavior before retiring Company/Person readers or loaders.

- [x] Review scalar engine and loader history with GoF; preserve function-based dispatch. Verified GoF/history review; independent reviewers agree; 2026-10-03 18:29 ET.
- [x] Demonstrate current number/bool gaps against the loader. Verified scalar oracle reproduced precision, boolean, float-truncation and Unicode gaps; 2026-10-03 18:29 ET.
- [x] Add exact integer conversion, explicit invalid/overflow policies and integer-derived boolean output; preserve JSON source kinds without changing existing text/number behavior. Verified 47 Rust tests and 43 focused Python tests passed; 2026-10-03 18:29 ET.
- [x] Compare Python scalar behavior including booleans, native float truncation, integer precision, signed bounds, decimal text/Unicode/underscores, missing and invalid values. Verified 43 focused Python tests passed, including Unicode decimal and adjacent-character oracle; 2026-10-03 18:29 ET.
- [x] Add full 14 content-column filing contract; compare pinned captured receipts. Verified 1,000 distinct captured filings / 107,197 rows matched; committed content-qualification.json; 2026-10-03 18:29 ET.
- [x] Verify immutable worker output and independent reparse, plus installed native binding. Verified 110 engine tests passed in 327.30s, including installed integer-records PostgreSQL 16 trial; 2026-10-03 18:29 ET.
- [ ] Bundle implemented syntax in the skill, independent code review, PR and all CI suites/gate.
- [ ] Artifact context, CIK and bounded-history equivalence; complete all 18 filing columns.
- [ ] Company/Person classification, reference addresses, grouping and source read blocks.
- [ ] GLEIF full positive/failure equivalence and reader retirement.
- [ ] Installed empty-store full proof: 6,414 Companies, 3,052 CIK+LEI, unchanged replay.

## Design review

The evaluator dispatch and primitive value boundary are stable. Add source-kind metadata to the existing tree, keep the language's enum/functions, and share integer conversion for both integer and boolean output. Class-based Strategy/Visitor layers would add no demonstrated maintenance benefit. Existing text/number primitives and custom boolean return behavior remain unchanged.

## Dependency scope

Python 3.12's integer lexical behavior includes Unicode 15.0 decimal digits. A pinned Unicode general-category table must match that version and be tested against the actual Python runtime before claiming lexical parity. Signed 64-bit output reflects the platform's PostgreSQL/Arrow integer boundary; overflow needs a declared policy and must never saturate.

## Independent review

Standards and Spec reviewers found no scoped blockers. Separate raw/ordinary JSON tree translation is a nonblocking maintenance concern; retaining it preserves existing behavior during qualification. Final PR CI remains pending.
