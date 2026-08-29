# 10 — The Atomic Write-Path Cutover (Indivisible)

**What to build:** DuckDB Retirement's Ticket 01 (wayfinder decision) locked
this in as one atomic code change, no transition-window flag:
`register-task-definition` bakes a specific-revision ARN into each deploy's
Step Functions JSON, and executions already running keep using the old
revision for their whole lifecycle (confirmed AWS behavior) — so mid-flight
executions are isolated for free, without needing a feature flag.

In one deploy: the production write path stops writing `silver.duckdb`
entirely (Snowflake landing zone only). At the same moment, all consumers
that Tickets 02–03 and 05–08 already proved work against their new targets
switch over together:

- The 11 operational bookkeeping tables (checkpoints, sync-state, leases,
  run audit trail) — repointed at the live Postgres store from
  [Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md)/
  [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md)/
  [Ticket 13](13-rewrite-cross-store-join-sites.md)/
  [Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md)/
  [Ticket 15](15-repoint-remaining-bookkeeping-callers.md), actually
  provisioned live by [Ticket 04](04-provision-live-bookkeeping-postgres.md)
- MDM's reader ([Ticket 05](05-cutover-mdm-reader-to-snowflake.md))
- Gold's Python builders retiring in favor of dbt `ref()`ing dbt silver
  (external `dbt-gold-silver-rewiring` chain)
- **All five** acquisition-family `*_silver_acceptance.py` modules —
  `silver_acceptance.py` (filing_artifact, the only one wired into a live
  scheduled command today) plus its four dormant siblings
  (`reference_catalog_`, `company_facts_`, `submissions_`,
  `adv_bulk_dataset_silver_acceptance.py`) — per
  [Ticket 09](../duckdb-retirement/issues/09-account-for-silver-acceptance-in-write-path-cutover.md)'s
  resolution on the wayfinder map (a different ticket set — the wayfinder
  map's own Ticket 09, not this cutover ticket set's Ticket 09)

**Do not split this ticket further along consumer lines.** Ticket 01's own
rollback answer is explicit: rolling back only the write path "would
silently starve already-cutover readers of fresh data, not error loudly."
Splitting "cut over the acquisition modules" or "cut over MDM's reader" into
separate deploy steps from the write-path flip reintroduces exactly that
failure mode. This ticket is one deploy, or it isn't the ticket the map
decided on.

**Blocked by:**
[Ticket 01](01-rewrite-daily-index-checkpoint-qualify-clause.md),
[Ticket 02](02-move-bookkeeping-tables-to-snowflake-postgres.md),
[Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md),
[Ticket 13](13-rewrite-cross-store-join-sites.md),
[Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md),
[Ticket 15](15-repoint-remaining-bookkeeping-callers.md),
[Ticket 04](04-provision-live-bookkeeping-postgres.md),
[Ticket 05](05-cutover-mdm-reader-to-snowflake.md),
[Ticket 06](06-retire-bootstrap-batch-sharding.md),
[Ticket 07](07-retire-ddl-generator-scripts.md),
[Ticket 08](08-build-table-specific-reconciliation-tooling.md), and the
`dbt-gold-silver-rewiring` map's full 7-ticket chain — every consumer must
already be proven against Snowflake before this ticket flips the write path
off DuckDB. Note Ticket 04 specifically: the bookkeeping Postgres instance
must be live, not just coded, before this deploy — the write path cannot
repoint to a store that doesn't exist yet.

**Status:** blocked

- [ ] Production write path (`_run_submissions_bronze_then_silver` and every
      other DuckDB-write call site) no longer writes `silver.duckdb`
- [ ] The 11 bookkeeping tables read/write the live Postgres store, not
      `SilverDatabase`/DuckDB, confirmed in this same deploy
- [ ] All five `*_silver_acceptance.py` modules read/write Snowflake, not
      `SilverDatabase`/DuckDB
- [ ] MDM's reader and gold's builders are confirmed live on Snowflake in
      this same deploy (not a separate one)
- [ ] Deployed via `register-task-definition` baking a specific-revision
      ARN — confirmed in-flight executions at deploy time keep using the
      prior revision for their whole lifecycle
- [ ] [Ticket 08](08-build-table-specific-reconciliation-tooling.md)'s
      tooling is ready to run against the post-cutover state immediately
      (handed to [Ticket 11](11-post-cutover-reconciliation-gate.md))
