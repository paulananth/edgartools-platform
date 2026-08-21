# What is the latest complete gold run we must keep?

Type: grilling
Status: resolved
Blocked by: none

## Question

GSD GOLD-01 says: delete historical `warehouse/gold/` `run_id=` copies and
keep the latest complete run per table by `LastModified` (not UUID sort).
Research already warned that gold is written table-by-table and `run_id` is
a UUID, so max `LastModified` per table can keep a *partial* run and delete
the last *complete* snapshot.

Decide:

1. Keep, per table, the current object with the newest `LastModified` under
   `warehouse/gold/{table}/run_id=`.
2. Keep one `run_id` that is the newest **complete** set (every expected
   table present, or a finished run manifest) and delete other `run_id=`
   prefixes.
3. Something else — name the completeness signal (manifest key, export
   pointer, Snowflake load receipt).

Canonical Silver and Snowflake gold dynamic tables are out of this
question. This is only warehouse gold parquet copies used as reclaim
keep-set.

## Answer

**Option 2.** Keep one `run_id`: the newest **complete** gold run.

Completeness signal: a run is complete when it has a current (`IsLatest=true`)
hive parquet object for every gold table present in the listing. Table names
come from `warehouse/gold/{table}/run_id=...` keys. `warehouse/gold/runs/`
manifests are not hive tables and are not the signal.

Newest among complete runs is the run whose newest current parquet
`LastModified` is greatest. Do not sort UUID/`run_id` strings except as a
tie-break after `LastModified`.

A newer **partial** run (missing at least one table) is reclaimable. Its
newest table must not displace the last complete snapshot.

If no run covers every table, fall back to the union of per-table newest
`LastModified` `run_id=` values so the keep-set cannot go empty.

Implemented in
`edgar_warehouse/infrastructure/warehouse_duplicate_reclaim.py`
(`_gold_keep_run_ids` / `select_candidates`).
