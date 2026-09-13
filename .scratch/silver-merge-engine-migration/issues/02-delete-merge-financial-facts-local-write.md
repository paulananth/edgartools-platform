# 02 — Delete `merge_financial_facts`'s local DuckDB write, passthrough to `landing_export`

**Type:** task

**Status:** resolved (2026-09-13), implemented together with [Ticket 03](03-postgres-scratch-store-for-derived-and-flags.md)
(same passthrough helper serves all three entity-facts tables).

## Question

[Ticket 01](01-choose-replacement-engine-and-migration-order.md)'s Final Answer established
that `sec_financial_fact` has no confirmed in-process reader anywhere — its local DuckDB write
in `SilverDatabase.merge_financial_facts` is dead compute. Delete it.

## Answer

- `merge_financial_facts` kept as a thin method (two callers, both pass `(rows, sync_run_id)`;
  inlining would duplicate the default/stamp/NOT NULL logic) — it now calls
  `_record_landing_passthrough`: no `_merge_rows_bulk`, no staging table, no QUALIFY/ON
  CONFLICT. Rows are recorded with the old values_fn defaults (`period_start` sentinel,
  `form_type`, `segment`) plus `ingested_at`/`valid_from`/`valid_to`/`is_current`. A row
  missing a NOT NULL column raises before anything is recorded.
- `company_facts_silver_acceptance.py`'s read-back was deleted, not replaced: the producer
  settles VERIFIED once its rows are recorded. The retire call it gated went too (Ticket 01's
  third CORRECTION). Note the driver still opens its `SilverDatabase` with no landing export,
  so its writes go nowhere — already true since Ticket 10; noted in the module docstring.
- The DuckDB `CREATE TABLE` DDL stays: schema migrations 001/002/010/011 and
  `PROTECTED_TABLE_REGISTRY` still reference the table, and `merge_candidate_into_canonical`
  (live via `silver_event_reducer.py`) still merges it.

**Not yet live-verified** — needs a prod entity-facts run after deploy.
