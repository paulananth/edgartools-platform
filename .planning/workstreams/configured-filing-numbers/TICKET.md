# Configured filing numbers

Continue ticket 21 and the filing column checklist. Complete source outputs and failure behavior before retiring Company/Person readers or loaders.

- [ ] Review scalar engine and loader history with GoF; preserve function-based dispatch.
- [ ] Demonstrate current number/bool gaps against the loader.
- [ ] Add exact integer conversion, explicit invalid/overflow policies and integer-derived boolean output; preserve JSON source kinds without changing existing text/number behavior.
- [ ] Compare Python scalar behavior including booleans, native float truncation, integer precision, signed bounds, decimal text/Unicode/underscores, missing and invalid values.
- [ ] Add full 14 content-column filing contract; compare pinned captured receipts.
- [ ] Verify immutable worker output and independent reparse, plus installed native binding.
- [ ] Bundle implemented syntax in the skill, independent code review, PR and all CI suites/gate.
- [ ] Artifact context, CIK and bounded-history equivalence; complete all 18 filing columns.
- [ ] Company/Person classification, reference addresses, grouping and source read blocks.
- [ ] GLEIF full positive/failure equivalence and reader retirement.
- [ ] Installed empty-store full proof: 6,414 Companies, 3,052 CIK+LEI, unchanged replay.

## Design review

The evaluator dispatch and primitive value boundary are stable. Add source-kind metadata to the existing tree, keep the language's enum/functions, and share integer conversion for both integer and boolean output. Class-based Strategy/Visitor layers would add no demonstrated maintenance benefit. Existing text/number primitives and custom boolean return behavior remain unchanged.

## Dependency scope

Python 3.12's integer lexical behavior includes Unicode 15.0 decimal digits. A pinned Unicode general-category table must match that version and be tested against the actual Python runtime before claiming lexical parity. Signed 64-bit output reflects the platform's PostgreSQL/Arrow integer boundary; overflow needs a declared policy and must never saturate.
