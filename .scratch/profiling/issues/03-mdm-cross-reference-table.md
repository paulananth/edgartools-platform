# 03 MDM cross-reference table

Type: task. Phase: A. Blocked by: 01a. Map: [map](../map.md). Plan: [plan](../plan.md).

## Checklist

- [x] GoF consult: healthy; extract one helper for the identifiers and cross-references loops in adapters.py; registration checks as more flat lines; name the omit-when-empty hash rule 2026-10-06 07:01 ET
- [ ] Table + contract syntax
- [ ] Write and read back; never joins
- [ ] Existing assertion ids stay byte-identical (golden test); a body with cross-references hashes differently and validates (added 2026-10-06 07:01 ET)
- [ ] Registration refuses an unknown cross-reference format and a namespace that is also an identifier or an activated binding namespace (added 2026-10-06 07:01 ET)
- [ ] Never-joins test with a control: two sources sharing only a cross-reference stay two entities; the same value as an identifier binds them (added 2026-10-06 07:01 ET)
- [ ] View over stage_record follows survivors, keeps unbound records, lookup uses an index (EXPLAIN on a populated table), COMMENT ON every column (added 2026-10-06 07:01 ET)
- [ ] REFERENCE.md contract syntax; profiling's `proposal: cross_reference` points at it (guard first) (added 2026-10-06 07:01 ET)
- [ ] ~~Cross-references on the live SEC contracts~~ out of scope: a new reading of the source, with the operator's approval (added 2026-10-06 07:01 ET)
- [ ] ~~SEC's placeholder EIN 000000000 (15,061 records)~~ follow-up: needs a format that drops all-zero values before EIN becomes a cross-reference (added 2026-10-06 07:01 ET)
- [ ] ~~History (--as-at/--as-of) for cross-references~~ the view answers "now"; ticket 05 decides whether history is needed (added 2026-10-06 07:01 ET)
- [ ] Review, PR, CI, merge on word
