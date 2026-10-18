# A combine reads many readings under one name

Priority: 112, tier 2, the recreation proof (raised by ticket 14's slice 2, 2026-10-18). Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: claimed (Claude, 2026-10-18 ET, branch `claude/t112-combine-reading-lists`). Blocked by: none. Unblocks: 14 (slice 2, OpenFIGI's chain run by `rules test`).

## Why

A composed Bookkeeping input names at most 16 prior units by slot, nested once (`config.COMPOSE_SLOTS`, `COMPOSE_DEPTH`), and each OpenFIGI answers file needs its own lookup set from its own request reading. So an answers unit holds at most 16 files. The full capture has 3,837 CUSIP and 3,877 ISIN request files: about 240 answers units per kind. Their reduce must read all of them, but a combine's `readings` mapped each name to one reading, and `openfigi/reduce.yaml` names `answers_1`..`answers_8`. A rules file cannot name 240. With a list under one name, a list slot (1..256 units) fills `answers`, and the ceiling is 16 x 256 = 4,096 files per kind a run.

## Design

GoF consult (2026-10-18): one shared normalizer, `source_readings.receipts(value)`, a receipt or an ordered list of 1..`READINGS` (256, now one named constant), used by the combine's load loop and the reduction's per-source loop; the loops stay in the callers. The output names the mapping as given. `last` over a listed name is refused, as over several sources (the order across units is the list's; kept refused until that is needed and tested).

## Checklist

- [x] GoF consult (2026-10-18)
- [x] `source_readings.receipts` and `READINGS`; combine and reduction read a listed name in order as one; `last` refused over a list. `tests/engine/test_combine_reading_lists.py` 5 passed (a reduction over a listed name equals one reading of the rows; a combination joins every listed reading; `last` refused; 0 and 257 refused); named affected engine tests 141 passed, 21 s (2026-10-18 18:17 ET)
- [ ] Three-axis review, PR, CI, merge
- [x] Learning → skill: data-platform COMBINING.md, Inputs: a name may list 1..256 readings
