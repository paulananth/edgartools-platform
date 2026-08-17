# DuckDB Retirement

Labels: wayfinder:map

## Destination

DuckDB is fully retired from the platform: the production write path stops
writing `silver.duckdb` entirely (Snowflake landing zone only), MDM's
`ShardedSilverReader`, gold's Python builders (`gold_models.py`), and
`bootstrap-batch`'s CIK-sharded write mechanism all move to reading/writing
Snowflake, and the local test suite plus `generate_silver_landing_ddl.py`'s
schema-introspection tooling drop their DuckDB dependency too — nothing in
the codebase still imports `duckdb`. Done when someone can execute the
retirement without hitting an undecided design question; this map does not
implement it.

## Notes

- **This map exists because the decision was already made but never
  implemented.** The closed
  [silver-snowflake-migration](../silver-snowflake-migration/map.md) map
  already decided the target architecture and that DuckDB *should* retire
  (its Ticket 03: gold's Python builders retire in favor of dbt `ref()`ing
  dbt silver; MDM's `ShardedSilverReader` retires in favor of Snowflake
  GRANTs) — but that map was decision-spec only and stopped at "someone can
  implement the migration without further architecture debate." Live
  evidence as of this map's charting (2026-08-16) confirms the deferred
  half is still outstanding: an `mdm run` task in flight this session is
  still reading DuckDB shards directly (`silver_shard_hydrated` events
  against `s3://.../warehouse/silver/sec/shards/shard-N.duckdb`), the write
  path still dual-writes to both DuckDB and the Snowflake landing zone
  (that map's Ticket 02), and `gold_models.py`'s ~20 Python builders are
  still live. Treat that map's Decisions-so-far as settled input, not
  something to re-derive — this map picks up exactly where it stopped:
  cutover/rollback mechanics, which that map's own "Not yet specified"
  flagged as unresolved.
- **Grilling establishing this map's scope (2026-08-16, before charting):**
  - Trigger: finishing the deferred migration, not a fresh cost/incident
    driver.
  - Scope: full retirement, everywhere — including the local dev/test
    suite and `generate_silver_landing_ddl.py`'s DuckDB-introspection DDL
    generator, not just production. This is the most expensive part of the
    scope: most of this repo's unit tests build real `SilverDatabase`-backed
    DuckDB fixtures (e.g. `tests/unit/test_bronze_recovery_no_db_row.py`,
    `test_gold_models_streaming.py`, `test_sharding.py`) and lose their
    current fixture strategy entirely under this scope.
  - `bootstrap-batch`'s CIK-sharded hydrate/publish mechanism
    (`pipeline-throughput-architecture`'s Ticket 12, a real measured
    76s→3.2s optimization) is explicitly in scope here rather than left as
    a separate decision — same underlying DuckDB storage being retired.
  - Timing: chart now; execution waits for the in-flight mdm-ahead-of-silver
    work (task #134/#155, an `mdm run` + backfill-sweep verification) to
    settle, not for a longer Snowflake-silver soak period. Snowflake silver
    itself only had its first successful prod dbt run hours before this map
    was charted — genuinely new, not yet proven under repeated/varied load.
  - This map stands alone rather than reopening the closed migration map —
    matches how `mdm-ahead-of-silver` referenced that same map without
    merging into it; keeps each map's Decisions-so-far a bounded, skimmable
    index.
- Domain: same files as the closed migration map —
  `edgar_warehouse/silver_store.py`, `edgar_warehouse/silver_support/
  sharded_reader.py`, `edgar_warehouse/silver_protection.py`,
  `edgar_warehouse/serving/gold_models.py`, `edgar_warehouse/mdm/` sharded
  silver reads, `infra/scripts/generate_silver_landing_ddl.py`. Also in
  scope now: `tests/unit/` DuckDB-backed fixtures (broad — grep
  `SilverDatabase(` and `duckdb.connect(` across `tests/` before scoping
  Ticket 05), and `edgar_warehouse/application/warehouse_orchestrator.py`'s
  `bootstrap-batch` CIK-sharded hydrate/publish path.
- This repo has documented incidents from getting cross-stage
  sequencing/coupling assumptions wrong (CLAUDE.md's
  "INSTITUTIONAL_HOLDS/EMPLOYED_BY" and "Manifest-pipeline ownership +
  cursor-syntax incident" 5-whys) and from provisioning steps that weren't
  committed/re-runnable scripts (CLAUDE.md's "MDM Snowflake mirror schema
  lost on cutover"). Every ticket here should weigh both explicitly — this
  is a full storage-layer retirement, the highest-blast-radius kind of
  change this repo makes.
- Use `/gof-refactor-reviewer` before any ticket proposing to restructure
  `silver_store.py`, `silver_protection.py`, or `gold_models.py` — same
  standing preference the closed migration map and
  `pipeline-throughput-architecture` both carried for this exact code.
- Mode: decision-spec only (wayfinder default, not overridden).
  Implementation is a separate, later effort — same as the closed
  migration map.

## Decisions so far

- [Decide the Local Dev/Test Replacement Strategy](issues/05-decide-local-dev-test-replacement-strategy.md) — of the 56 DuckDB-touching test files (measured, not estimated), only ~35-38 are the real decision: operational bookkeeping (leases, checkpoints, idempotency gates) that isn't SEC content or MDM data and has to live somewhere queryable. ~8 need no SQL engine at all (S3-mechanics tests using `.duckdb` as an example blob), ~5-6 retire to dbt, ~4 get rewritten against Ticket 02's answer instead. The remainder ports to plain SQLite (stdlib, no ORM/SQLAlchemy) — dialect-checked clean except 13 `QUALIFY` clauses needing rewrite to `WHERE rn = 1` form.
- [Decide the Cutover Validation Standard](issues/07-decide-cutover-validation-standard.md) — reused this repo's existing Production Release Readiness vocabulary rather than inventing a new one: digest-based Table-Specific Reconciliation per table (not full diff, not count-only), bounded case-selected reruns including one real-scale table (not a calendar soak), automated fail-closed assertion gating a required human approval. Ticket 01 explicitly excluded — no "old" to diff against for future data, deferred to when it resolves. Unblocks Tickets 02, 03, and 04.
- [Decide MDM's ShardedSilverReader Replacement Mechanics](issues/02-decide-mdm-reader-replacement-mechanics.md) — hard cutover, no transition window (minimal Protocol, 6 call sites, zero DuckDB-dialect SQL found in any MDM silver-read query). Credential activation: reuse the existing shared `EDGARTOOLS_PROD_LOADER` secret as a secondary role rather than provisioning a dedicated one (operator's explicit choice, knowingly reintroducing some write-role read overlap). "Resolution matches" means Ticket 07's row-level digest standard on the read, not identical `entity_id` values — same match decision + confidence score per input row.
- [Decide Gold's Python-Builder Retirement Mechanics](issues/03-decide-gold-builder-retirement-mechanics.md) — per-table hard swap (not a synchronized parallel-run window), since dbt gold turned out not to be wired to dbt silver at all (22/23 models still source from the Python-builder mirror) and per-table complexity varies too much to gate uniformly. Parity compares business-key content, not surrogate-key columns — DuckDB's `hash()`/Python `sha256` key derivations have no Snowflake equivalent. Concrete mechanics sequenced as 7 vertical-slice tickets under `../dbt-gold-silver-rewiring/issues/`.
- [Decide bootstrap-batch's Sharding Mechanism Fate](issues/04-decide-bootstrap-batch-sharding-fate.md) — the CIK-sharded DuckDB hydrate/publish mechanism retires entirely; `bootstrap-batch` already dual-writes to the landing zone today, and that write is per-run Parquet (no shared mutable object), so it carries none of the contention the shard mechanism exists to solve. Reprocessing still does useful work under append-only + latest-wins collapse (a parser-fix rerun genuinely changes content, doesn't just re-emit duplicates). `MaxConcurrency` stops being contention-bounded once there's no shard file to promote — new ceiling is the Fargate vCPU quota, exact number deferred to implementation-time tuning. Bookkeeping-storage and shared shard-infra deletion both deferred to Ticket 01.
- [Decide Where Operational Bookkeeping Lives Once DuckDB Retires](issues/08-decide-operational-bookkeeping-storage-target.md) — 12 of 41 DuckDB tables (checkpoints, sync-state, leases, run audit trail) have no Snowflake landing-zone replication path today, discovered while investigating Ticket 01. Target: Snowflake's native Postgres service, reusing MDM's already-proven pattern, applied uniformly to all 12. Operator explicitly chose to start the new store empty rather than migrate existing state — accepted cost, recorded plainly: every currently paused/completed CIK reverts to pending and becomes eligible for full re-bootstrap on the first post-cutover run, the exact reactivation hazard seed-universe-narrow-hydrate's Ticket 05 flagged, now happening deliberately platform-wide.
- [Decide the Production Write-Path Cutover Sequence](issues/01-decide-write-path-cutover-sequence.md) — atomic code change, no transition-window flag: register-task-definition bakes a specific-revision ARN into each deploy's Step Functions JSON, and executions already running keep using the old revision for their whole lifecycle (confirmed AWS behavior), so mid-flight executions are isolated for free. Rollback is all-or-nothing across write path + MDM's and gold's reader cutovers together — rolling back only the write path would silently starve already-cutover readers of fresh data, not error loudly. DuckDB file disposition extends the existing `expire-noncurrent-silver-canonical-versions` lifecycle-rule precedent: bounded retention on the final current version, then archive/delete.

- [Decide the DDL Generator's Non-DuckDB Schema Source](issues/06-decide-ddl-generator-schema-source.md) — corrected the ticket's own premise first: the generator never introspected a live DuckDB instance, only an ephemeral `:memory:` one seeded from the `silver_store._DDL` string, used purely as a SQL-parsing engine. A second caller with the identical pattern was found (`generate_silver_dbt_models.py`). Both retire entirely rather than gaining a successor generator — 13 of 14 Snowflake bootstrap SQL files are already hand-maintained, this generator was the one exception, and future schema changes become a direct hand-edit like everywhere else in this repo. Distinct from Ticket 08's bookkeeping-table SQLAlchemy models (different tables, different platform, genuine ORM use case there).

## Not yet specified

(none yet — breadth-first frontier below covers everything surfaced during
charting; new fog may surface as tickets resolve)

## Frontier

(none — every ticket on this map is resolved; the map is ready to hand off
for implementation)

## Out of scope

<!-- none yet -->
