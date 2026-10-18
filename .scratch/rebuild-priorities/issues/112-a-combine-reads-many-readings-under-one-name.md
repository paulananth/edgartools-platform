# A combine reads many readings under one name

Priority: 112, tier 2, the recreation proof (raised by ticket 14's slice 2, 2026-10-18). Map: [Rebuild priorities](../map.md).

Type: task (engine). Status: done (#1094 merged 2026-10-18 18:39 ET). Blocked by: none. Unblocks: 14 (slice 2, OpenFIGI's chain run by `rules test`).

## Why

A composed Bookkeeping input names at most 16 prior units by slot, nested once (`config.COMPOSE_SLOTS`, `COMPOSE_DEPTH`), and each OpenFIGI answers file needs its own lookup set from its own request reading. So an answers unit holds at most 16 files. The full capture has 3,837 CUSIP and 3,877 ISIN request files: about 240 answers units per kind. Their reduce must read all of them, but a combine's `readings` mapped each name to one reading, and `openfigi/reduce.yaml` names `answers_1`..`answers_8`. A rules file cannot name 240. With a list under one name, a list slot (1..256 units) fills `answers`, and the ceiling is 16 x 256 = 4,096 files per kind a run.

## Design

GoF consult (2026-10-18): one shared normalizer, `source_readings.receipts(value)`, a receipt or an ordered list of 1..`READINGS` (256, now one named constant), used by the combine's load loop and the reduction's per-source loop; the loops stay in the callers. The output names the mapping as given. `last` over a listed name is refused, as over several sources (the order across units is the list's; kept refused until that is needed and tested).

## Checklist

- [x] GoF consult (2026-10-18)
- [x] `source_readings.receipts` and `READINGS`; combine and reduction read a listed name in order as one; `last` refused over a list. `tests/engine/test_combine_reading_lists.py` 5 passed (a reduction over a listed name equals one reading of the rows; a combination joins every listed reading; `last` refused; 0 and 257 refused); named affected engine tests 141 passed, 21 s (2026-10-18 18:17 ET)
- [x] Three-axis review (2026-10-18 18:26 ET). GoF: `mdm.prepare` uses the shared `receipts` and `READINGS` instead of its own copy (done). Standards: a reading listed twice is refused (it would count its rows twice), the listed artifacts are gathered once, the row budget across a list and `confirm` over a list are tested (done). Spec: COMBINING.md says `last` is refused for a reduction only (a combination group's `last` takes the last listed reading's row), a positive control for `last` over one reading (done); 8 tests in the file, named affected engine tests 143 passed
- [ ] ~~A Bookkeeping list slot filling a listed name, end to end~~ deferred to ticket 14 slice 2: by reading the code (`engine.py` fills a list slot with a list of receipts); OpenFIGI's target run by `rules test` is its test
- [x] PR, CI, merge (#1094 merged 2026-10-18 18:39 ET)
- [x] Learning → skill: data-platform COMBINING.md, Inputs: a name may list 1..256 readings
