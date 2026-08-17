# Decide Where Operational Bookkeeping Lives Once DuckDB Retires

Type: grilling
Status: resolved
Blocked by: None

## Question

Discovered while investigating [Decide the Production Write-Path Cutover
Sequence](01-decide-write-path-cutover-sequence.md): not every DuckDB table
has a Snowflake landing-zone replication path today. 30 of 41 tables are
covered by `silver_landing_export.py`'s `@track_landing_rows`/
`@track_landing_row` decorators on `SilverDatabase`'s `merge_*`/`upsert_*`
methods — append-only SEC content, correctly modeled as landing-zone rows.
12 are not decorated at all, because they aren't append-only content — they
are genuinely mutable, read-then-conditionally-write operational state:
`sec_company_sync_state`, `sec_source_checkpoint`, `pipeline_run`,
`pipeline_run_lease`, `sec_sync_run`, `sec_parse_run`,
`discovery_checkpoint`, `sec_daily_index_checkpoint`,
`stg_daily_index_filing`, `gold_manifest`, `sec_reconcile_finding`,
`schema_migration`.

Concretely: `_apply_submission_snapshot_to_silver`
(`warehouse_orchestrator.py:4831`) calls `db.get_source_checkpoint(...)` to
decide whether a submission's content already matches what's on file
(`main_same`/`pagination_same`/`all_same`), then `db.upsert_source_checkpoint(...)`
(an `ON CONFLICT (source_name, source_key) DO UPDATE`) to record the new
state. `db.upsert_company_sync_state(...)` similarly does a per-CIK
`ON CONFLICT (cik) DO UPDATE` with `COALESCE`-based partial merges
(tracking_status, latest_filing_date_seen, etc. — the safety-net guard
`seed-universe-narrow-hydrate`'s Ticket 05 confirmed is still load-bearing).
`pipeline_run_lease` backs the `sec_fetch_active` cross-command lease
mechanism. None of this has anywhere to live once no DuckDB file exists
anywhere — the Snowflake landing zone's append-only, per-run-Parquet shape
(no shared mutable object, by design — see Ticket 04's answer) is
structurally the wrong fit for read-modify-write upsert semantics on a
shared key.

Decide: where does this 12-table operational bookkeeping move to? Candidate
shapes worth weighing (not exhaustive):
- **A Snowflake SQL table**, written via `MERGE`/`UPDATE` over the same
  connection already used for landing-zone/dbt writes — one platform, but
  Snowflake's warehouse compute is batch/analytics-shaped, not built for
  frequent small single-row upserts (every submission-processing call does
  a per-CIK checkpoint read+write).
- **Snowflake's native Postgres service** — reusing the exact pattern
  already proven for MDM's operational store (`EDGARTOOLS_PROD_MDM`,
  cut over from AWS RDS specifically to consolidate onto Snowflake — see
  CLAUDE.md's "MDM database" note). Genuine OLTP shape, but adds a live
  network dependency to a hot path that's currently pure local-file I/O.
- **DynamoDB** — a natural fit for CIK-keyed/checkpoint-keyed lookups with
  no join requirements, but introduces a third storage platform purely for
  this narrow need, cutting against this migration's own "eliminate a
  storage surface" spirit.
- **A small SQLite (or similar) file, still S3-promoted** — technically
  satisfies "no more `import duckdb`," but keeps the exact ETag-guarded
  promote-contention architecture this whole map exists to retire, just
  under a different file format and much smaller scope. Reusing Ticket 05's
  SQLite choice here would be a scope stretch — that ticket picked SQLite
  specifically as a *local test fixture* stand-in, not a production store.

Also decide: does every one of the 12 tables move to the same target, or do
some (e.g. `pipeline_run`/`sec_sync_run`, pure audit trail with no
read-back-for-decision use) tolerate a different, simpler treatment than
others (e.g. `sec_company_sync_state`/`sec_source_checkpoint`, read on the
hot path for every idempotency check)?

## Deliverable

A decided storage target (or explicitly per-table targets, if they
shouldn't be uniform) for the 12 non-landing-zone-tracked DuckDB tables,
specific enough that [Decide the Production Write-Path Cutover
Sequence](01-decide-write-path-cutover-sequence.md) can build its cutover
mechanics on top of a known destination rather than an open one.

## Answer

- **Target: Snowflake's native Postgres service** — the same operational
  pattern already proven for MDM's store (`EDGARTOOLS_PROD_MDM`, cut over
  from AWS RDS specifically to consolidate onto Snowflake; see CLAUDE.md's
  "MDM database" note). Real OLTP semantics for per-CIK/per-checkpoint-key
  read-then-upsert access, no new storage platform introduced, reuses an
  already-provisioned credential/connection pattern (`MDM_DATABASE_URL`-style
  DSN, distinct from the HTTPS Snowflake SQL connection) rather than
  standing up DynamoDB or accepting Snowflake SQL warehouse compute for
  frequent tiny single-row upserts.
- **Uniform for all 12 tables** — one write/read path, one credential, one
  operational surface, rather than splitting by access pattern. All 12 are
  small in absolute scale (per-CIK, per-run, or per-checkpoint-key, not
  filing-content scale), so there's no measured throughput case for a split.
  Whether this reuses the existing `EDGARTOOLS_PROD_MDM` instance directly
  (new tables in the same database) or a small dedicated instance is an
  implementation-time choice, not decided here.
- **Cutover starts empty — explicit operator choice, overriding the
  recommended "migrate existing state."** Recorded plainly with its real
  cost, not just "let it rebuild": `sec_company_sync_state.tracking_status`
  is the safety-net guard `seed-universe-narrow-hydrate`'s Ticket 05
  confirmed still load-bearing — it's specifically what stops a
  `paused`/`completed` company from being silently reactivated. Starting
  the new Postgres store empty means every CIK's lookup falls through to
  the existing default (`{"tracking_status": "bootstrap_pending"}`,
  `_apply_submission_snapshot_to_silver`'s fallback), so **every currently
  paused or completed company reverts to pending and becomes eligible for a
  full re-bootstrap-scale re-evaluation on the first post-cutover run** —
  not just a generic "re-evaluate sync state" cost, but specifically the
  exact reactivation failure mode Ticket 05 flagged as a real hazard to
  guard against, now happening deliberately across the whole tracked
  universe at once instead of being a bug. Accepted knowingly by the
  operator; Ticket 01 (or whichever ticket implements this cutover) should
  account for the resulting SEC-call volume spike and, if that blast radius
  turns out to be unacceptable at implementation time, revisit this
  specific sub-decision rather than silently mitigating it.
