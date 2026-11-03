# 175: The silver check engine learns the kinds a silver table needs

Priority: 175. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 17:46 ET (found while building ticket 169's first checks from DataKitchen TestGen's test types).

Type: task. Status: resolved. Blocked by: none. Related: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md).

## Question

The silver check engine runs three kinds: `identifier`, `in_set` (text columns only) and `one_value`. TestGen's 89 test types (research note `docs/research/datakitchen-testgen-test-types-2026-11-02.md`) show what a silver table usually needs next. Which kinds does the platform add, and in what order?

## Parts

- [x] Rank the missing kinds (2026-11-02 18:44 ET): a silver table's `PRIMARY KEY` (`database.py`, from the spec's `key`) already refuses a repeated key and a null key column, so TestGen's unique-key and required types are covered by the table and need no kind (the load fails instead of flagging). What is left, by checks unlocked: (1) `in_set` over a `BIGINT` column (operator, 2026-11-02 18:44 ET: "no integer only bigint"), one check now (`window_years`); (2) a column-order kind (`period_start` not after `period_end`: `company_fact`, `company_line_item`); (3) a value present only with a reason kind (`value` null exactly when `null_reason` is filled: `company_line_item`, `company_measure`); (4) a date-not-in-the-future bound, which needs the load's clock; (5) volume, pattern and second-table kinds, none needed yet
- [x] GoF consult, then the first kind with its tests (2026-11-02 18:44 ET): leave the dispatch tables (`ARGUMENTS`, `_FAILS`; three kinds, one added is two entries and a guard); first kind = `in_set` over a whole-number column, `tests/unit/test_silver_writer.py` (whole-number values only, text still text, a flag or fraction refused)
- [x] Each new check declared on the three tables, with an invented-rows test (2026-11-03 12:49 ET): `window_years_known` on `company_measure` (2026-11-02); the two kinds that were left: `not_after` (`period_start_not_after_end` on `company_fact` and `company_line_item`) and `reason_if_empty` (`empty_value_has_reason` on `company_line_item` and `company_measure`), in `silver/checks.py` with their refusals (types, columns, the reason is text) in `tests/unit/test_silver_writer.py` and the three tables' checks in `tests/unit/test_company_facts_quality_checks.py`. Failing before: the engine refused both kinds ("A silver check is one of ['identifier', 'in_set', 'one_value']"). A table whose spec Silver already registered takes the changed spec as a new table; the local store holds no Silver. Rank items 4 (a date not in the future, needing the load's clock) and 5 (volume, pattern, second table) stay unbuilt: no table needs them yet
- [x] Learning → skill (2026-11-03 12:49 ET): `skills/data-quality/SKILL.md` names `not_after` and `reason_if_empty` beside the other three kinds and says a date order is `not_after`
