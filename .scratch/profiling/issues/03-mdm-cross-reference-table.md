# 03 MDM cross-reference table

Type: task. Phase: A. Blocked by: 01a. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult: healthy; extract one helper for the identifiers and cross-references loops in adapters.py; registration checks as more flat lines; name the omit-when-empty hash rule 2026-10-06 07:01 ET
- [x] Table + contract syntax (contract `cross_references` + `cross_reference_formats`; migration 005: view mdm.cross_reference, GIN index, mdm.cross_reference_lookup; REFERENCE.md documents it) 2026-10-06 07:16 ET
- [x] Write and read back; never joins (tests/integration/test_clean_cross_reference_postgres.py on PG16: written through the Merge Stage, read back by lookup) 2026-10-06 07:16 ET
- [x] Existing assertion ids stay byte-identical (golden test); a body with cross-references hashes differently and validates (added 2026-10-06 07:01 ET) (golden id computed on main; tests/mdm/test_clean_cross_reference.py) 2026-10-06 07:16 ET
- [x] Registration refuses an unknown cross-reference format and a namespace that is also an identifier or an activated binding namespace (added 2026-10-06 07:01 ET) (5 refusals tested; an own-name namespace such as src_lei passes) 2026-10-06 07:16 ET
- [x] Never-joins test with a control: two sources sharing only a cross-reference stay two entities; the same value as an identifier binds them (added 2026-10-06 07:01 ET) (same value: binds as an identifier, joins nothing as a cross-reference; two records sharing only a cross-reference stay two companies) 2026-10-06 07:16 ET
- [x] View over stage_record follows survivors, keeps unbound records, lookup uses an index (EXPLAIN on a populated table), COMMENT ON every column (added 2026-10-06 07:01 ET) (merged record found at its survivor; waiting record found with no entity; index scan counted; every column commented, checked by test_mdm_schema_comments) 2026-10-06 07:16 ET
- [x] REFERENCE.md contract syntax; profiling's `proposal: cross_reference` points at it (guard first) (added 2026-10-06 07:01 ET) (REFERENCE.md adapter table; data-profiling SKILL.md links it; guard clean) 2026-10-06 07:16 ET
- [ ] ~~Cross-references on the live SEC contracts~~ out of scope: a new reading of the source, with the operator's approval (added 2026-10-06 07:01 ET)
- [ ] ~~SEC's placeholder EIN 000000000 (15,061 records)~~ follow-up: needs a format that drops all-zero values before EIN becomes a cross-reference (added 2026-10-06 07:01 ET)
- [ ] ~~History (--as-at/--as-of) for cross-references~~ the view answers "now"; ticket 05 decides whether history is needed (added 2026-10-06 07:01 ET)
- [x] Adding a cross-reference is a new version, not a new source code (it never decides which record is which); written in REFERENCE.md (added 2026-10-06 07:16 ET)
- [x] Three-axis review findings applied (format check once, one hash-rule comment, lookup STRICT with qualified parameters, index comment, EXPLAIN test, own-name namespace test, another kind's ids note) (added 2026-10-06 07:16 ET) (Standards, Spec and GoF: no hard violations, no bugs; all small findings applied; per-kind views test now lists cross_reference; PG16: 46 affected integration tests pass; plain EXPLAIN on 400 records reads the index) 2026-10-06 07:19 ET
- [ ] Review, PR, CI, merge on word (review done 2026-10-06 07:19 ET; PR, CI and merge pending)
