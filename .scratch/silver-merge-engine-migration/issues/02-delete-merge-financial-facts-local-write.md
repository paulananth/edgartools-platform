# 02 — Delete `merge_financial_facts`'s local DuckDB write, passthrough to `landing_export`

**Type:** task

## Question

[Ticket 01](01-choose-replacement-engine-and-migration-order.md)'s Final Answer established
that `sec_financial_fact` has no confirmed in-process reader anywhere — its local DuckDB write
in `SilverDatabase.merge_financial_facts` (`silver_store.py:3147`) is dead compute. Delete it.

**What to build:**

- Remove `merge_financial_facts`'s DuckDB write body (the `_merge_rows_bulk` call, the
  `stg_sec_financial_fact` staging table, the `QUALIFY ROW_NUMBER()`/`ON CONFLICT` SQL) —
  keep the method itself only long enough to preserve its existing `landing_export.record(...)`
  call (the raw, pre-merge rows, unchanged), or move that call directly to the two call sites
  (`fundamentals_ingest.run_bootstrap_entity_facts`,
  `acquisition/company_facts_silver_acceptance.py`) if that's cleaner given the shape of each
  caller — judgment call for whoever implements this, not pre-decided here.
- Confirm via `/gof-refactor-reviewer` before editing (CLAUDE.md hard rule) whether keeping a
  thin `merge_financial_facts` wrapper vs. inlining the `landing_export.record` call at each
  caller is the better shape, given there are exactly two callers.
- `company_facts_silver_acceptance.py`'s own read-back verification
  (`SELECT DISTINCT accession_number FROM sec_financial_fact WHERE cik = ? AND accession_number
  IN (...)`) becomes meaningless once nothing writes that table locally — this check needs its
  own fate decided here too: either delete it (nothing to verify against locally anymore — the
  real verification, if wanted, would need to check what actually reached the Snowflake landing
  export) or replace it with a landing-export-based check. Don't leave it silently checking an
  empty table and reporting false failures.
- `sec_financial_fact`'s DuckDB `CREATE TABLE` DDL itself: leave in place or remove? Check
  whether any other DuckDB consumer (schema migrations, `ShardedSilverReader`, test fixtures)
  still expects this table to exist before removing the DDL — likely yes for schema-migration
  history reasons (same reasoning CLAUDE.md's DuckDB Retirement 5-whys entries give for keeping
  dead-but-historically-relevant registry membership); confirm rather than assume.

**"Done" bar** (per Ticket 01's Final Answer): equivalent regression coverage to the existing
tests exercising `merge_financial_facts` (update them for the new no-DuckDB-write contract,
don't delete the coverage) plus a live-verified production write showing the landing export
still receives the rows correctly.

## Blocked by: none — Ticket 01 is resolved, this is now the frontier.
