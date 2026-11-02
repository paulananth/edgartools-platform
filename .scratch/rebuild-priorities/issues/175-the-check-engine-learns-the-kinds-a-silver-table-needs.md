# 175: The silver check engine learns the kinds a silver table needs

Priority: 175. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 17:46 ET (found while building ticket 169's first checks from DataKitchen TestGen's test types).

Type: task. Status: in progress (first kind done); the rest is ranked below. Blocked by: none. Related: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md).

## Question

The silver check engine runs three kinds: `identifier`, `in_set` (text columns only) and `one_value`. TestGen's 89 test types (research note `docs/research/datakitchen-testgen-test-types-2026-11-02.md`) show what a silver table usually needs next. Which kinds does the platform add, and in what order?

## Parts

- [x] Rank the missing kinds (2026-11-02 18:44 ET): a silver table's `PRIMARY KEY` (`database.py`, from the spec's `key`) already refuses a repeated key and a null key column, so TestGen's unique-key and required types are covered by the table and need no kind (the load fails instead of flagging). What is left, by checks unlocked: (1) `in_set` over a `BIGINT` column (operator, 2026-11-02 18:44 ET: "no integer only bigint"), one check now (`window_years`); (2) a column-order kind (`period_start` not after `period_end`: `company_fact`, `company_line_item`); (3) a value present only with a reason kind (`value` null exactly when `null_reason` is filled: `company_line_item`, `company_measure`); (4) a date-not-in-the-future bound, which needs the load's clock; (5) volume, pattern and second-table kinds, none needed yet
- [x] GoF consult, then the first kind with its tests (2026-11-02 18:44 ET): leave the dispatch tables (`ARGUMENTS`, `_FAILS`; three kinds, one added is two entries and a guard); first kind = `in_set` over a whole-number column, `tests/unit/test_silver_writer.py` (whole-number values only, text still text, a flag or fraction refused)
- [ ] Each new check declared on the three tables, with an invented-rows test: `window_years_known` on `company_measure` done (2026-11-02 18:44 ET, `tests/unit/test_company_facts_quality_checks.py`); the order and reason kinds (2) and (3) wait for their own PRs
- [ ] Learning → skill: `data-quality` names the new kinds
