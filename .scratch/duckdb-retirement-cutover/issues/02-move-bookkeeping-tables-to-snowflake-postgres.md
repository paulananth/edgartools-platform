# 02 — Build the Bookkeeping Store Layer

**Split from the original Ticket 02 during implementation (2026-08-28).**
Mapping the real interface surface found the original single ticket was the
largest change in this whole cutover set — 30 distinct `SilverDatabase`
methods across 11 tables, 3 cross-store SQL joins with no existing plan, and
~15 caller files, on top of live DDL against prod. Split into three:

- **This ticket (02)** — the store layer only: SQLAlchemy models, the store
  class's method surface, and the provisioning script. No caller repointing,
  no live DDL.
- [Ticket 03](03-rewrite-cross-store-joins-and-repoint-callers.md) — rewrite
  the 3 cross-store join sites and repoint every caller at the new store.
  **Further split during Ticket 03's own implementation (2026-08-29)** into
  Ticket 03 (new store methods + instantiation convention),
  [Ticket 13](13-rewrite-cross-store-join-sites.md) (the join sites),
  [Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md)
  (`warehouse_orchestrator.py`'s 50+ call sites), and
  [Ticket 15](15-repoint-remaining-bookkeeping-callers.md) (everything
  else) — see Ticket 03's own current body for why. References below to
  "Ticket 03" for the join sites / `get_table_counts` merge logic
  specifically now mean Ticket 13 / Ticket 14 respectively; left as
  originally written elsewhere in this file since the caller-repointing
  scope as a whole still traces back to the original Ticket 03 split.
- [Ticket 04](04-provision-live-bookkeeping-postgres.md) — actually run the
  provisioning script against live prod Snowflake, last, once 02 and the
  full Ticket 03/13/14/15 caller-repointing chain are tested and reviewed.

**What to build:** DuckDB Retirement's Ticket 08 (wayfinder decision)
decided these 11 tables — checkpoints, sync-state, leases, and the run audit
trail, none of them SEC content or MDM data — have no Snowflake
landing-zone replication path today and must move to Snowflake's native
Postgres service, reusing the exact provisioning pattern
`bootstrap-prod-mdm.sh` already proved for MDM's operational store:

- `sec_company_sync_state`
- `sec_source_checkpoint` (its bare DuckDB `_DDL` string is missing a
  `bronze_path TEXT` column that exists live via a runtime `ALTER TABLE ...
  ADD COLUMN` — `upsert_source_checkpoint` writes it, so the new model
  must declare it as a real column from the start, not copy the bare DDL
  literally)
- `pipeline_run`
- `pipeline_run_lease`
- `sec_sync_run`
- `sec_parse_run`
- `discovery_checkpoint`
- `sec_daily_index_checkpoint`
- `stg_daily_index_filing`
- `gold_manifest`
- `sec_reconcile_finding`

(`schema_migration`, originally counted alongside these 12, is excluded —
it's `SilverDatabase`'s own internal DuckDB-migration ledger with no meaning
once DuckDB itself is gone; it does not migrate anywhere.)

**Interface decision (grilled with the operator before this split):** a new
dedicated store object, not `SilverDatabase` routing these tables internally
to Postgres. SQLAlchemy-backed, mirroring `edgar_warehouse/mdm/database.py`'s
*skeleton* (a `Base`, connection-settings-from-env, a session factory) — not
its 1157 lines of MDM-specific models. Matches CLAUDE.md's existing note
that SQLAlchemy is correct for MDM's own Postgres OLTP store (as opposed to
Snowflake's dbt-only SQL interface, which this is not); this new store is
architecturally the same shape as MDM's, just a different table set. Chosen
over keeping `SilverDatabase`'s method signatures because that option
doesn't actually avoid the hard part (the 3 cross-store join sites bypass
the method interface entirely regardless) and would leave `SilverDatabase`
as a two-backend facade fighting [Ticket 12](12-duckdb-retirement-cleanup.md)'s
"delete all DuckDB code" cleanup.

**Method surface to replicate — corrected during implementation (2026-08-28)
against the real current line numbers.** The ticket's original list named 36
methods (not 30 — a prose miscount, not a real ambiguity) and missed 2
scope problems a full extraction pass found. Net: **34 methods** port into
this ticket as literal 1:1 translations, plus one narrowed reimplementation:

`get_source_checkpoint`, `upsert_source_checkpoint`,
`upsert_company_sync_state`, `get_company_sync_state`,
`seed_company_sync_state_bulk`, `get_tracked_ciks`, `get_ciks_with_bronze`,
`finish_discovery_ciks`, `acquire_pipeline_run_lease`,
`release_pipeline_run_lease`, `mark_pipeline_run_lease_backstop_overdue`,
`get_pipeline_run_lease`, `get_sync_run`, `start_pipeline_run`,
`complete_pipeline_run`, `record_pipeline_verification`, `get_pipeline_run`,
`start_sync_run`, `complete_sync_run`, `start_parse_run`,
`complete_parse_run`, `get_parse_run`, `get_pending_checkpoint_dates`,
`get_discovery_checkpoint`, `claim_discovery_ciks`,
`get_daily_index_filings`, `upsert_daily_index_checkpoint`,
`get_daily_index_checkpoint`, `get_last_successful_checkpoint_date`,
`merge_daily_index_filings`, `record_gold_manifest` (plus its required
private helper `_latest_gold_manifest_for_table`), `get_gold_manifest`,
`insert_reconcile_findings`, `get_reconcile_findings`. Read each method's
current body in full before reimplementing — this list is the map, not a
substitute for reading the actual lease-expiry, upsert-conflict, and
JSON-serialization logic each one carries.

**2 methods from the original list are excluded, not ported here:**
- `get_all_filing_texts` — the ticket's own text hedged ("verify against the
  real method body") and the hedge was warranted: it queries
  `sec_filing_text`, a genuine SEC-content table, not one of these 11. Zero
  external callers found (grep across `edgar_warehouse/` and `scripts/`).
  Leave it out of this store's surface entirely; if `sec_filing_text` needs
  a home post-cutover, that's a different, unrelated ticket.
- `get_company_identity_ciks` — a **4th cross-store join**, missed by the
  original 3-join mapping: it joins `sec_company_sync_state` (in scope)
  against `sec_company`/`sec_company_ticker` (SEC-content tables staying in
  DuckDB) in one SQL statement. Same failure shape as the 3 joins
  [Ticket 13](13-rewrite-cross-store-join-sites.md) owns — added there, not
  built here.

**1 method needs a narrowed version, not a literal port:**
- `get_table_counts` — the real method spans the *entire* DuckDB database
  (~37 tables, content and bookkeeping mixed) via DuckDB-only
  `duckdb_tables()` introspection, which has no Postgres equivalent anyway.
  This ticket builds a scoped-down version returning counts for only these
  11 tables (trivial: one `SELECT COUNT(*)` per known table name, no
  introspection needed). The original method's full multi-store contract —
  merging this store's counts with DuckDB's remaining content-table counts
  for the one real caller (`warehouse_orchestrator.py:665`) — is
  [Ticket 14](14-repoint-warehouse-orchestrator-bookkeeping-callers.md)'s
  job.

Also port the trivial `_json_text` static helper (`json.dumps(value,
default=str, sort_keys=True)`) if columns like `pipeline_run.arguments_json`
stay JSON-as-TEXT rather than moving to a native SQLAlchemy `JSON` column
type (an open implementation choice, not dictated by this ticket).

**Provisioning script:** a committed, re-runnable script (not a manual
one-off session, per this repo's own "MDM Snowflake mirror schema lost on
cutover" incident) that creates the new Snowflake Postgres instance (or
schema within one, matching whichever `bootstrap-prod-mdm.sh` actually
provisions for MDM) plus all 11 tables, additive grants only (no `REVOKE
CURRENT GRANTS`, per "Manifest-pipeline ownership"). Since the store starts
**empty** by explicit operator decision (see below), a single idempotent
`CREATE TABLE IF NOT EXISTS` script is proportionate — this is not a
populated-database migration needing MDM's full multi-version migration
runner; mirror `09_mdm_mirror_schema.sql`'s shape (`infra/snowflake/sql/
bootstrap/`), the committed-script fix this repo already used for the
identical class of gap. Do not run this script in this ticket — write and
unit-test it against a local Postgres/SQLite target; live execution is
[Ticket 04](04-provision-live-bookkeeping-postgres.md).

**Watch for the `snowflake_write` RESET ACCESS behavior** documented in
CLAUDE.md: this platform re-grants `snowflake_write`'s baseline DML access
to a table as a side effect of rotating *either* `application`'s or
`snowflake_admin`'s credentials — a prior `bootstrap-prod-mdm.sh` run
silently reopened this exact fence on every invocation until it was fixed.
Whatever this new provisioning script's last step is, [Ticket 04](
04-provision-live-bookkeeping-postgres.md) must verify with a live
`has_table_privilege` sweep *after* that last step, not just after the DDL.
Also check whether `mdm check-fence` (`edgar_warehouse/mdm/fence_monitor.py`)
discovers these new tables automatically — it discovers from
`pg_class`/`pg_roles`, so it may or may not depending on the owner role this
script chooses.

**Operator-accepted cost, stated explicitly so it isn't rediscovered as a
surprise during rollout:** the new store starts **empty**, not migrated from
existing DuckDB state. Every currently paused/completed CIK reverts to
pending and becomes eligible for full re-bootstrap on the first post-cutover
run — the same reactivation hazard `seed-universe-narrow-hydrate`'s Ticket 05
flagged, now happening deliberately, platform-wide, by explicit operator
choice (DuckDB Retirement map, Ticket 08's answer).

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] A committed, re-runnable provisioning script exists
      (`infra/scripts/provision_bookkeeping_schema.py`, schema/tables for
      all 11 tables via `Base.metadata.create_all`, additive grants),
      written and tested but **not yet run against live Snowflake** —
      that's Ticket 04
- [x] The new store class exposes all 34 methods listed above (plus the
      narrowed `get_table_counts`), matching
      `SilverDatabase`'s current signatures, backed by SQLAlchemy models
      against Postgres (tested against SQLite/local Postgres, per this
      repo's existing MDM test convention)
- [x] Migration mechanism is a single idempotent script, not a copy of
      MDM's full multi-version migration runner — justified above by the
      store starting empty
- [x] Tests covering lease acquisition (including backstop-overdue marking
      and expiry), checkpoint read/write, and run-audit writes (pipeline
      run start/complete/verification, sync run, parse run) pass against
      the new store — 58 tests, `tests/bookkeeping/`, all green
- [x] The empty-start behavior (every CIK reverts to pending) is documented
      in the deploy runbook (`docs/runbook.md`'s "Bookkeeping Store
      Cutover" gotcha), not just this ticket, so whoever runs
      [Ticket 04](04-provision-live-bookkeeping-postgres.md) isn't
      surprised by the reactivation scale
