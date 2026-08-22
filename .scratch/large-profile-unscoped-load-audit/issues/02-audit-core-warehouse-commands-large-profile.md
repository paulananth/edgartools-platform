# 02 — Audit bootstrap-full/targeted-resync/full-reconcile/bootstrap/daily-incremental/bootstrap-next for the unscoped-load shape

Type: task
Status: resolved

## Question

These six commands (`bootstrap-full`, `targeted-resync`, `full-reconcile`,
`bootstrap`, `daily-incremental`, `bootstrap-next`) all resolve to `large`
via `command_task_profile()` and funnel through shared
`warehouse_orchestrator.py` code paths (bronze/silver capture,
`SOURCE_EXPORT_COMMANDS` gold build). Audit for the MANAGES_FUND-shape
risk — unscoped full load of a shared table/dataset before scoping is
known — that is **not already covered** by an existing resolved map.

Known-covered ground (don't re-litigate, but do confirm each still
actually applies to the current code, since maps can go stale):
- `gold-refresh`'s `build_gold()` full-materialization risk — fixed by
  `iter_gold_tables()` streaming (gold-build-memory-reliability, ticket 01).
- `daily_incremental`'s task-sizing gap that caused the original
  `sec_thirteenf_holding` OOM — fixed (gold-build-memory-reliability,
  ticket 03; task-profile-consolidation).
- `bootstrap-next`'s artifact-fetch throttle/idempotency gaps — fixed
  (artifact-throttle 5-whys, bronze-recovery-with-no-DB-row 5-whys, both
  in CLAUDE.md).

What's genuinely unaudited for *this specific* shape (an unscoped ORM/DB
hydration before scoping — the MANAGES_FUND pattern, not a DuckDB/S3
buffering pattern): whether any of these six commands' silver-write or
MDM-adjacent code paths (e.g. `mdm_entity_backfill.py`'s
`BackfillMdmEntityIds` step, wired into both `daily_incremental` and
`bootstrap`) load an unbounded set of rows/entities before knowing which
subset the current run actually touches. Check
`edgar_warehouse/mdm_entity_backfill.py` specifically — it's the one
MDM-Postgres-adjacent piece embedded in these six commands' state
machines and has never been checked against this shape.

If a genuine gap is found, fix it the same way MANAGES_FUND/
INSTITUTIONAL_HOLDS were (batch-scope, release-between-batches,
red-before-green test). If nothing new is found, record that explicitly
with the evidence checked — a clean bill of health is a valid, useful
answer here.

**Addendum (found while investigating ticket 04, moved here since
`bootstrap`/`daily_incremental` are this ticket's exact scope):** 3 more
`large`-profile states live inside `write_warehouse_mdm_gold_definition`
(the shared bash function building both commands' state machines) that
were originally, incorrectly attributed to `load_history` in ticket 04's
first draft — `ReleaseSecFetchLease`, `ReduceIdentityRefresh`
(`reduce-identity-refresh`, part of `bootstrap`/`daily_incremental`'s own
`ResolveCompanyIdentityBounded`/Stage0-company-identity sub-map — a
different, sibling stage from `load_history`'s own since-removed
Stage0CompanyIdentity, per CLAUDE.md), and one hardcoded `wh_large_arn`
`SeedUniverse` state (~line 3487 as of this addendum, distinct from
`load_history`'s own already-correctly-routed SeedUniverse). Check these
for the same unscoped-load shape alongside the `mdm_entity_backfill.py`
finding above.

## Blocked by

None — can start immediately.

## Answer

Found and fixed one genuine, real gap; confirmed the rest safe with live
evidence.

**`edgar_warehouse/mdm_entity_backfill.py` — genuine gap, fixed.**
`_fetch_pending_rows` issued one unbounded `SELECT * FROM {table} WHERE
mdm_entity_id IS NULL` + `cursor.fetchall()` per table, no LIMIT, full-row
width. Live Snowflake measurement (2026-08-22): today's pending sets are
all tiny (sec_company 5,752; reporting_owner 44; non_derivative_txn 36;
derivative_txn 1; adv_filing 0; adv_private_fund 0) — but the underlying
**total table sizes** (live-measured against the real canonical shards,
`s3://edgartools-prod-warehouse-690839588395/warehouse/silver/sec/shards/`)
show the real risk: `sec_adv_private_fund` alone is **1,579,876 rows** —
larger than MANAGES_FUND's own 563,631-row OOM trigger — currently 0
pending only because MDM resolution has kept up so far. Exactly the "safe
until it isn't" shape INSTITUTIONAL_HOLDS's pre-emptive fix addressed for
its own 6.8M-row source table; a resolution outage, a large backfill event,
or a newly-added table could spike this table's pending set into the
hundreds of thousands, and the unbounded read would hold that many
full-row dicts in Python at once.

Fixed by adding keyset pagination (`_fetch_pending_rows_batches`,
`_ROW_CHUNK_SIZE=2000`) using each table's own real unique-key columns —
**not** uniformly CIK, since live schema inspection
(`DESC TABLE EDGARTOOLS_SILVER.SEC_ADV_PRIVATE_FUND`) showed
`sec_adv_private_fund` has no CIK column at all (only
`ADVISER_CRD_NUMBER`, a VARCHAR) — correcting the spec's original
CIK-range-batching assumption before writing any code. Snowflake supports
row-value tuple comparison directly (`(a,b) > (?,?)`, verified live), so
each table pages via `WHERE mdm_entity_id IS NULL AND (key_cols...) >
(last_seen...) ORDER BY key_cols LIMIT 2000` — forward-only keyset, not
OFFSET, since this sweep never mutates the source table in place (resolved
rows are re-emitted via a separate landing-export path). `backfill_pending_rows`
now processes and writes one batch's resolved rows at a time instead of
materializing every pending row across all 6 tables before writing
anything. `_lookup_entity_ids`'s existing 500-row Postgres-side chunking
(already correct) is untouched.

Tests: 2 new regression tests in `tests/mdm/test_entity_backfill.py` —
one proving genuine chunking (5 rows, chunk size forced to 2 → 3 bounded
`execute()` calls, each carrying `LIMIT 2`, not one unbounded fetch), one
proving batch-size independence (chunk size 1 vs 1,000 produce identical
resolved/pending counts and landing-export contents). Both confirmed red
without the fix (`git stash` on `edgar_warehouse/mdm_entity_backfill.py` —
`AttributeError: no attribute '_ROW_CHUNK_SIZE'`), green with it. All 6
pre-existing tests in the file still pass unmodified against the upgraded
`_FakeCursor`/`_FakeConnection` (now genuinely simulates keyset-pagination
SQL instead of unconditionally returning every configured row).

**`_run_submissions_bronze_then_silver` and what it calls — confirmed
clean, no fix needed.** Checked all 6 call sites' `ciks` arguments: line
1614 (`daily-incremental`'s `ResolveCompanyIdentityBounded`/discovery path)
windows via `impacted_ciks[cik_offset:][:cik_limit]` then
`db.claim_discovery_ciks`; lines 1681/1711 (`bootstrap`/`bootstrap-next`)
and 1751 route through `_resolve_bootstrap_target_ciks`, which applies
`ciks[cik_offset:][:cik_limit]` windowing — `bootstrap-full`/
`full-reconcile`'s apparently-unbounded case is `cik_limit=None` by
*design* (the entire point of "full"), not a scoping defeat; line 2278
(`load_history`'s per-window call) passes an already-windowed `cik_list`;
line 3227 (`targeted_resync`) passes `ciks=[cik]`, a single company.
Inspected `_capture_submission_bronze_snapshots` and
`_apply_submission_snapshot_to_silver`: every DB/S3 access inside both is
keyed by the current CIK or a specific file checkpoint (`db.get_company_sync_state(cik)`,
`db.get_source_checkpoint(...)`, `db.stage_submission(cik=cik, ...)`) —
no load of an unrelated shared table independent of the caller's CIK list.
Memory scales proportionally to the caller's own bounded (or intentionally
full-universe, for `bootstrap-full`) CIK list — the caller's *own* stated
scope, not an unrelated dataset loaded before scoping is known. This is
the DuckDB/S3-buffering shape the parent map's Notes explicitly separate
from this ticket's target (unscoped *independent* dataset hydration), not
a new instance of the MANAGES_FUND pattern.

**Addendum's 3 states, all confirmed — no fix needed.**
- **`ReleaseSecFetchLease`**: `edgar_warehouse/application/warehouse_orchestrator.py`'s
  `release-sec-fetch-lease` handler is a single `db.release_pipeline_run_lease(...)`
  call plus an event emission — no table read/hydration of any kind. Runs
  on `wh_large_arn` today, which is oversized for what it does, but that's
  a cost-sizing question (the `ecs-cost-sizing` map's territory), not an
  OOM-shape finding.
- **`ReduceIdentityRefresh`**: already fixed with exactly this map's
  established pattern, before this ticket existed. The script's own
  comment (line ~3767) states the OOM history directly: "a real prod run
  was OOM-killed (exit 137) on medium's 4096MB mid-merge on the largest
  protected table, even after the code-level fix... that stopped holding
  every verified candidate as Python bytes for the whole reducer call" —
  release-readiness ticket 83's fix bounded what the reducer holds in
  memory (the batch-scope-release pattern this whole map is checking for),
  and the `wh_large_arn` move was explicit "belt-and-suspenders headroom"
  *on top of* that code fix, not a substitute for it.
- **`SeedUniverse`** (hardcoded `wh_large_arn`, line ~3487) — **CORRECTION
  (found while preparing Ticket 04, recorded here and in Ticket 04's own
  Answer):** my original conclusion below was incomplete. The
  full-canonical-`silver.duckdb`-hydrate *cost* genuinely is the
  DuckDB/S3-buffering shape owned by `seed-universe-narrow-hydrate`, out
  of scope here — that part of the original conclusion stands. But a
  *separate*, already-decided question was missed: task-profile-
  consolidation tickets 06/07 already decided
  `command_task_profile('seed-universe') == "medium"` and already ported
  that routing to `write_load_history_definition`'s own SeedUniverse
  (ticket 07) — this state's hardcode was simply never updated to match,
  exactly the "fixed elsewhere, not yet ported here" pattern this map
  exists to catch. **Fixed**: `write_warehouse_mdm_gold_definition` now
  routes this state's task ARN through `command_task_profile("seed-universe")`
  (guarded to only compute for `workflow_name != "daily_incremental"`,
  the only case with a SeedUniverse state), mirroring
  `write_load_history_definition`'s exact pattern. See Ticket 03's Answer
  for the full fix + test detail (found and fixed during that ticket's
  own preparation, but belongs to this ticket's scope).
  ~~The full-canonical-`silver.duckdb`-hydrate cost is the DuckDB/S3-
  buffering shape, explicitly owned by the already-active
  `seed-universe-narrow-hydrate` wayfinder map... not re-litigated here~~
  — superseded by the correction above; struck through, not deleted, so
  the original reasoning trail stays visible.

Full `tests/mdm/` + `tests/unit/` suites: 1413 passed, 4 skipped. Not yet deployed — this ticket's mandate is investigate-and-fix in the
codebase; deployment is a separate, explicit follow-up.
