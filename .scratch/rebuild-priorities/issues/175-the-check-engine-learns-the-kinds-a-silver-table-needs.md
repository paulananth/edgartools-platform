# 175: The silver check engine learns the kinds a silver table needs

Priority: 175. Map: [Rebuild priorities](../map.md). Opened 2026-11-02 17:46 ET (found while building ticket 169's first checks from DataKitchen TestGen's test types).

Type: task. Status: open, not started. Blocked by: none. Related: [169](169-company-financials-run-through-bookkeeping-and-the-change-journal.md).

## Question

The silver check engine runs three kinds: `identifier`, `in_set` (text columns only) and `one_value`. TestGen's 89 test types (research note `docs/research/datakitchen-testgen-test-types-2026-11-02.md`) show what a silver table usually needs next. Which kinds does the platform add, and in what order?

## Parts

- [ ] Rank the missing kinds by the checks they unlock on `company_fact`, `company_line_item` and `company_measure`: unique key (the three tables' keys), required (key columns), a value null only with a `null_reason`, `period_start` not after `period_end`, `filed` not in the future, `in_set` over integer columns (`window_years`)
- [ ] GoF consult, then the first kind with its tests (one test per kind), as its own PR
- [ ] Each new check declared on the three tables, with an invented-rows test
- [ ] Learning → skill: `data-quality` names the new kinds
