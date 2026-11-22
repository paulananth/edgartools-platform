# 17: The silver writer loads without a staging table

Status: open
Type: task

Operator, 2026-11-22, asked what the TEMPORARY privilege part of ticket 14 meant, then ruled: "no staging table needed remember 7 wastes".
The writer (`edgar_warehouse/silver_writer/relational.py`, `DatabaseSink.write`) creates a temporary table per delivery on PostgreSQL, loads the
delivery into it and merges that into `silver.<table>`. That moves every row twice (Transport and Over-processing, the seven wastes of the
data-platform skill) and needs the `TEMPORARY` privilege, which the no-DDL rule says a worker should not hold.

## What the staging table does today (read from the code)

1. Finds a key delivered more than once (a refusal).
2. Finds the rows the table lacks (insert), the rows whose values differ (count, then update) and, for append tables, refuses a changed row.
3. Updates the MDM id and quality columns where they differ.
4. For a snapshot table, deletes the rows the delivery does not hold, after refusing an empty delivery.

## Ruling (operator, 2026-11-22)

"why do we have a staging before silver the staging is part of source processing all that silver needs is final list of tables".
Source processing owns the final rows of a table, so it owns a key delivered twice; silver applies the rows by key. Silver's own
duplicate check and staging table are the same work done a second time (Over-processing).

## What silver still has to do, and what is open

- [ ] Apply by key, idempotently, in batches: insert a missing key, update a changed one, leave an equal one (a retry lands the same rows again with no change). Append tables refuse a changed row.
- [ ] Where the duplicate-key refusal now lives: in source processing. Finding (read 2026-11-22): a Source Extract does not guarantee it. The source-contract engine rejects duplicate JSON keys and header names, not a table's silver key; the source-contract spec (section 13.1) only *proposes* a validator that an adapter's record key columns are unique, and `source.combine` groups and joins by declared key without a uniqueness check. Silver's check is today the only one, so it stays until source processing refuses a repeated key (a declared check in the contract or in `source.combine`), proved by a test at the source extract.
- [ ] Snapshot tables (three of the registered specs): who removes a row the final list no longer holds. Recommendation: source processing hands the removal with the list, since it holds the previous final list; silver deletes by key.

## Decision (operator, 2026-11-22: "recommend a declared uniqueness check in the source contract")

A source contract declares the key of each table it reads, and the engine refuses a source extract whose table repeats it. What I found when
scoping it: the contract spec's `silver:` block names a `key`, but the sources in the repository no longer carry that block; the key of a
silver table lives in its registered spec (`rules/silver/*.yaml`), and the engine's Rust crate never reads a key. So the declaration is new
in `read.tables.<table>`, and a catalog check refuses a contract whose declared key differs from the registered silver spec's key (one fact
written twice must be proved equal, not trusted). The check is on one source extract, one captured file: a key repeated across two files is
a later delivery of the same row, which the per-key apply already leaves unchanged. A refusal names the table and the key columns, never a value.

## Checklist

- [x] Spec: `docs/specs/source-contract/spec.md` section 8.4 gains `key` on a table and the `repeated_key` refusal; section 13.1's proposed validator now points to it 2026-11-22 17:29 ET
- [x] Test first at the source extract: `crates/source-contract/tests/table_key.rs` failed (a repeated key was read; a key naming an unknown column was accepted), passes now; the crate's 237 tests pass 2026-11-22 17:29 ET
- [x] The engine enforces it: `check_key` after a table's rows are built, a table-level rule like `record_count` (GoF consult: not a per-record check, which sees one row); the set holds one key per kept row of one source extract, which the engine already holds in memory and bounds by `max_records` 2026-11-22 17:29 ET
- [ ] The Python side: rebuild the engine wheel and run the Python tests that load contracts
- [x] The check: a landed table must declare its silver table's key, equal to the spec's (`rules/shape.py`, where every target's steps are built, so every load and `rules check` refuse a mismatch); `test_a_landed_table_without_its_silver_key_is_refused` failed first (no refusal) 2026-11-22 17:42 ET
- [x] Local proof on one source with both MDM and silver, `iapd.adv` (operator: "pick a source that has both mdm and silver test it locally"): `custody_facts` declares `key: [filing_id, row]` (its silver spec's key); on a disposable local environment with the March 2026 ADV capture, custodians, mastering and silver loaded in 1 s, 19 s and 5 s; MDM holds 14,758 company masters; `silver.adv_custody` holds 15,482 rows, 15,482 distinct keys, each with its adviser's master id; a forced replay of the silver target left 15,482 rows (landing again changes nothing). Finding: the shared local server's rules store lacks `rules.policy` (older schema), so the proof ran on its own environment 2026-11-22 17:36 ET
- [x] Every source that lands in silver declares the key of each landed table: 19 tables in 9 contracts, each equal to its silver spec's key; all are append tables (the one snapshot table, `relationship`, is derived, not landed). 904 unit and architecture tests pass; `test_profiling_run.py::test_the_catalog_summary_names_and_counts_but_never_a_value` fails the same without this change 2026-11-22 17:42 ET


- [x] Consult `/gof-refactor-reviewer` (haiku) on the engine's key check: its own `key` field checked after the row loop, following `record_count` 2026-11-22 17:29 ET
- [ ] Consult `/gof-refactor-reviewer` on `relational.py` before the silver writer change
- [ ] Failing test first, at the public `write`: a PostgreSQL delivery on a role that holds no `TEMPORARY` privilege succeeds, and a duplicate key still refuses
- [ ] One batched upsert path for every load mode; MySQL's shared staging table is handled in the same change or kept as its own deferred part
- [ ] Storage-adapter tests on PostgreSQL and MySQL (`bash scripts/dev/adapter_test.sh`)
- [x] Decision (operator, 2026-11-22: "fix The line-item build also creates temporary tables", then "no temp table usage"): the line-item and measure builds run as one statement with `SET LOCAL enable_nestloop = off` (`financials/sql.py` `steered`), no temporary table. Measured on the company-facts cohort, one local store, identical rows (same digest): line items 96,807 rows in 27.7 s against 98.3 s with temporary tables; measures 168,360 rows in 12.3 s against 13.1 s. `test_company_line_item_silver.py` and `test_company_measure_silver.py` pass (13) 2026-11-22 18:00 ET
- [x] Audit of run-time DDL across `edgar_warehouse` (operator: "check everwhre to see if there are more places this is not acceptable"): temporary tables only in the financials builds (fixed) and the PostgreSQL silver writer (below); MySQL's silver writer stages in a permanent table made at registration (no DDL at run time, but a staging table: deferred with MySQL); every other `CREATE`/`ALTER`/`DROP` runs at init or registration as the owner; the profiling scripts' DDL is DuckDB on this machine, not a store. `tests/architecture/test_no_temporary_tables_at_run_time.py` guards it, failing first on both places; it still fails on the silver writer until it changes 2026-11-22 18:00 ET
- [x] Skills: company-financials (the build's rule), mdm-engineering (a key list is a bulk parameter, never a temporary table) 2026-11-22 18:00 ET
- [ ] The snapshot path stays: `company_line_item` and `company_measure` are rebuilt whole and the writer removes a row a delivery lacks (company-financials skill, "Running the facts through Bookkeeping"); the company-facts cohort is the proof before and after the writer change. Before (today's writer, the declared `company_fact` key in force, disposable local environment): 368 documents in 450 s; `company_fact` 5,134,979 rows for 329 companies, `company_line_item` 96,807, `company_measure` 168,360; no key repeated 2026-11-22 17:52 ET
- [ ] `TEMPORARY` revoked from the loader in provisioning and the reset script, tested (waits for the decision above)
- [ ] Standards, Spec and GoF review of the diff
- [ ] Learning → skill: name the skill line this ticket changed, or "none"
