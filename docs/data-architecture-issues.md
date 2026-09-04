# Data Architecture: 5-Whys Root-Cause Issues

## Architecture Flow

```
SEC EDGAR API
  ├─ daily form indexes ──┐
  ├─ per-CIK submissions ─┤
  ├─ filing documents ────┤
  └─ XBRL/companyfacts ───┤
                          ↓
              ┌─────────────────────┐
              │  Bronze (S3 raw)    │  ← immutable bytes, SHA256 dedup
              │  {bronze_root}/...  │
              └────────┬────────────┘
                       ↓
              ┌─────────────────────┐
              │  Staging (DuckDB)   │  ← temp tables, batch upsert
              │  stg_* temp tables  │
              └────────┬────────────┘
                       ↓
        ┌──────────────┴──────────────┐
        │  Silver (DuckDB, sharded×4) │  ← Branch A: sec_company, filings, etc.
        │  silver/sec/shards/shard-N  │  ← Branch B: sec_financial_fact, etc.
        │  silver/fundamentals/shard  │     (separate DB, no cross-ref integrity)
        └──────────────┬──────────────┘
                       ↓
              ┌─────────────────────┐
              │  Gold (PyArrow→S3)  │  ← Parquet star schema, rebuilt per run
              │  {storage_root}/    │  ← dim_*, fact_*, fundamentals passthrough
              │  gold/{table}/...   │
              └────────┬────────────┘
                       ↓
        ┌──────────────┴──────────────┐
        │  Snowflake native S3 pull   │  ← SNS manifest → external table
        │  dbt gold dynamic tables    │
        │  Streamlit dashboard        │
        └─────────────────────────────┘
```

---

## Issue 1 — Silver DuckDB sharding has no distributed write guarantees

**Observation:** Silver is 4 DuckDB shards partitioned by CIK range with no cross-shard transaction support.

**5-Whys:**
1. Sharding was introduced because the monolithic DuckDB file grew beyond manageable size
2. DuckDB doesn't natively support distributed writes, so sharding was a workaround
3. The architecture chose DuckDB for silver (embedded, easy to deploy) over a proper OLAP database
4. The project initially optimized for simplicity (single-node DuckDB) rather than scalability
5. Early design decisions prioritized fast local iteration over production data distribution

**Root cause:** Embedded OLAP DB chosen for simplicity, then sharded as an afterthought. Shards can diverge on concurrent writes with no two-phase commit or reconciliation.

**Affected files:**
- `edgar_warehouse/silver_store.py` — shard initialization and read/write paths
- `edgar_warehouse/silver_support/` — shard management
- `edgar_warehouse/application/sharding/` — shard routing
- `edgar_warehouse/config/warehouse_paths.properties` — `silver.shard.*` paths

---

## Issue 2 — Gold is a transient re-export, not a persistent curated layer

**Observation:** Every `gold-refresh` recomputes all dim/fact tables from scratch. Hash-based surrogate keys change if any silver row changes.

**5-Whys:**
1. Gold dimension tables are not stateful/SCD — they're rebuilt each run
2. The dimensional model was designed as an OLAP star schema for Snowflake, but the Parquet files are ephemeral per-run
3. DuckDB silver doesn't maintain slowly-changing dimension history natively
4. There's no dimensional warehouse that persists across runs; gold is purely a compute-on-read model
5. The architecture uses gold as an export format (Parquet files) rather than as a persistent curated layer

**Root cause:** Gold has no SCD management or versioned state — it's a compute-on-read star-schema projection, so there's no durable "gold state" to compare against.

**Affected files:**
- `edgar_warehouse/serving/gold_models.py` — all `_build_dim_*` / `_build_fact_*` functions
- `edgar_warehouse/serving/targets/snowflake.py` — export to Snowflake
- `edgar_warehouse/serving/targets/databricks.py` — export to Databricks
- `edgar_warehouse/config/warehouse_paths.properties` — `gold.table.*` paths

---

## Issue 3 — Branch A & B silver databases share no referential integrity

**Observation:** Main silver (`silver/sec/shards/`) and fundamentals silver (`silver/fundamentals/`) are separate DuckDB databases.

**5-Whys:**
1. Branch B (fundamentals) pipeline was added as a parallel workstream later
2. The fundamentals data (XBRL facts, 13F holdings) has very different volume/access patterns
3. Keeping them separate avoided schema conflicts with the existing silver schema
4. There's no unified silver-layer access pattern that spans both databases
5. No cross-DB foreign key support in DuckDB, so referential integrity between Branch A and Branch B tables is impossible

**Root cause:** DuckDB has no cross-database FK support. A `sec_financial_fact` row cannot reference `sec_company_filing` — consistency is only at the application level.

**Affected files:**
- `edgar_warehouse/silver_store.py` — DDL for `sec_financial_fact`, `sec_financial_derived`, etc.
- `edgar_warehouse/silver_support/session.py` — `open_silver_shard()` / `open_silver_database()`
- `edgar_warehouse/application/commands/bootstrap_fundamentals.py` — Branch B processing
- `edgar_warehouse/config/warehouse_paths.properties` — separate fundamentals path

---

## Issue 4 — No pipeline-level transaction or versioning

**Observation:** Idempotency is per-table (ON CONFLICT), per-command (checkpoints), per-manifest. No global transaction ties bronze→silver→gold together.

**5-Whys:**
1. Each stage has its own upsert logic, checkpoint table, or manifest
2. These mechanisms were added incrementally to handle specific failure modes
3. There's no global transaction or version number that ties bronze→silver→gold together
4. The pipeline is a set of independently-developed commands rather than a unified data pipeline
5. Early architecture focused on getting data flowing quickly (YAGNI approach to pipeline-wide guarantees)

**Root cause:** Incremental growth from independent commands, never unified into an end-to-end versioned pipeline. Cannot atomically roll back a failed multi-stage run.

**Affected files:**
- `edgar_warehouse/silver_store.py` — `sec_sync_run`, `sec_parse_run`, `sec_source_checkpoint`
- `edgar_warehouse/infrastructure/run_manifest_builder.py` — per-stage manifest building
- `edgar_warehouse/application/warehouse_orchestrator.py` — command orchestration
- `edgar_warehouse/config/warehouse_paths.properties` — `manifest.default.*` paths

---

## Issue 5 — Gold schema evolution requires coordinated breaking changes

**Observation:** PyArrow schemas are Python constants (e.g., `_DIM_COMPANY_SCHEMA`). Adding a column means recreating Snowflake external tables, updating dbt models, and redeploying simultaneously.

**5-Whys:**
1. Gold Parquet files track version only through `run_id` in the path, not embedded schema version
2. Snowflake external tables read these Parquet files directly — schema drift would break Snowflake
3. There's no schema registry or version negotiation between silver and gold
4. The gold model was designed as a fixed periodic export (like a snapshot), not an evolving dataset
5. No evolving-contract pattern was implemented (e.g., Avro schema registry, Protobuf, or Delta Lake)

**Root cause:** No schema registry, no backward-compatible evolution (Avro/Protobuf/Delta Lake). Gold schema = hard-coded Python constant.

**Affected files:**
- `edgar_warehouse/serving/gold_models.py` — all `_*_SCHEMA = pa.schema([...])` constants
- `infra/snowflake/dbt/edgartools_gold/` — dbt models consuming fixed Parquet schemas
- `infra/snowflake/streamlit/` — dashboard consuming dbt output

---

## Issue 6 — MDM overloaded with pipeline orchestration state

**Observation:** Gold commands fail unless `MDM_DATABASE_URL` is set. The entity-resolution system also tracks CIK universe status (`active`/`bootstrap_pending`).

**5-Whys:**
1. MDM tracks which companies are in the universe (active/bootstrap_pending)
2. The universe tracking was migrated from silver (`sec_tracked_universe`) to MDM PostgreSQL
3. MDM was added later and became the source of truth for CIK state
4. There was no single source of truth for "which companies to process"
5. The project added MDM for entity resolution and found it convenient to also use it for pipeline orchestration state

**Root cause:** MDM (entity resolution + Neo4j graph) was repurposed as the pipeline state machine, creating a tight operational coupling between analytical processing and entity management.

**Affected files:**
- `edgar_warehouse/infrastructure/warehouse_settings.py` — `MDM_DATABASE_URL` required for gold commands
- `edgar_warehouse/mdm/` — MDM CLI and universe tracking
- `edgar_warehouse/application/warehouse_orchestrator.py` — MDM-based CIK resolution

---

## Issue 7 — Serving export abstraction is leaky (Snowflake→Databricks retrofit)

**Observation:** Methods named `snowflake_export_*` and `serving_export_*` coexist with different callers. No clean interface between export generation and target delivery.

**5-Whys:**
1. The project started with Snowflake as the sole serving target
2. Databricks was added as a second target later
3. The naming was updated in env vars (`SERVING_EXPORT_ROOT`) but code paths were not fully refactored
4. There's no abstract export target interface — Snowflake and Databricks are separate modules with hard-coded Parquet paths
5. Multi-target serving was retrofitted onto an originally Snowflake-only export path

**Root cause:** Multi-target serving was overlaid on the original Snowflake-only export without defining an abstract target interface.

**Affected files:**
- `edgar_warehouse/serving/gold.py` — public surface with both naming conventions
- `edgar_warehouse/serving/targets/snowflake.py` — Snowflake-specific export
- `edgar_warehouse/serving/targets/databricks.py` — Databricks-specific export
- `edgar_warehouse/infrastructure/warehouse_settings.py` — `snowflake_export_root` compatibility alias
- `edgar_warehouse/infrastructure/dataset_path_catalog.py` — `snowflake_export_*` vs `serving_export_*` methods

---

## Issue 8 — Two independent filing discovery mechanisms with no unified schedule

**Observation:** `daily-incremental` uses form indexes; `bootstrap-*` uses per-CIK submissions API. Different checkpoint tables, different pagination, different retry behavior.

**5-Whys:**
1. Daily indexes provide aggregate view of all filings for a given business day
2. Per-CIK submissions API provides complete history per company
3. These serve different use cases (incremental catch-up vs. historical bootstrap)
4. They use different pagination and checkpoint strategies
5. The two discovery paths were developed independently for different phases of the project

**Root cause:** No unified "filing discovery" abstraction — leads to gaps or double-processing if not carefully coordinated.

**Affected files:**
- `edgar_warehouse/application/warehouse_orchestrator.py` — `_load_daily_form_index()` and `_bootstrap_company_submissions()` paths
- `edgar_warehouse/loaders/` — daily index loader vs submission loaders
- `edgar_warehouse/silver_store.py` — `stg_daily_index_filing` and `sec_daily_index_checkpoint` vs `sec_source_checkpoint`

---

## Issue 9 — No database migration framework; schema evolution via on-connect DDL

**Observation:** `_ensure_schema_evolution()` runs `ALTER TABLE ADD COLUMN IF NOT EXISTS` in the constructor of `SilverDatabase`.

**5-Whys:**
1. DDL changes needed to be applied without requiring migration scripts
2. DuckDB is embedded — no migration framework (Alembic) is used
3. The team preferred auto-migration over explicit migration management
4. The data model evolved rapidly during development
5. No migration management infrastructure was set up early on

**Root cause:** No Alembic/migration tooling. Schema changes are unversioned DDL patches that cannot be rolled back.

**Affected files:**
- `edgar_warehouse/silver_store.py` — `_ensure_schema_evolution()`, `_migrate_financial_period_end_pk()`
- `edgar_warehouse/silver_support/session.py` — `open_silver_database()` calls constructor

---

## Issue 10 — Destructive PK migrations risk data loss

**Observation:** `_migrate_financial_period_end_pk()` does `DROP TABLE {table}` + `CREATE TABLE IF NOT EXISTS` from DDL constant.

**5-Whys:**
1. DuckDB doesn't support ALTER TABLE to change primary key constraints
2. PK changes required table recreation
3. The schema evolution mechanism didn't handle progressive PK changes
4. No migration planning for DuckDB schema changes
5. Embedded DB (DuckDB) lacks native schema migration capabilities

**Root cause:** DuckDB's lack of PK constraint modification forces destructive schema changes (DROP TABLE + re-bootstrap) for PK modifications, risking data loss if re-bootstrap fails.

**Affected files:**
- `edgar_warehouse/silver_store.py` — `_migrate_financial_period_end_pk()`, `_migrate_financial_fact_period_start_pk()`
- Documentation: `docs/runbook.md`

---

## Issue 11 — No end-to-end data quality validation framework

**Observation:** There is now no automated upstream-drift check at all (is bronze in sync with SEC upstream?), let alone gold-vs-silver consistency, row count thresholds, or cross-table referential integrity. `full-reconcile` was this codebase's only such check — decommissioned entirely (zero executions ever, no schedule, `edgar_warehouse/reconcile.py` deleted) since this observation was first written, widening this gap rather than closing it.

**5-Whys:**
1. No upstream drift (bronze vs SEC) or downstream quality (silver vs gold, row counts, NULL ratios) is checked systematically anymore
2. Each team member relies on ad-hoc queries for quality checks
3. No quality SLAs or metrics are defined for the pipeline
4. The one prior systematic check (`full-reconcile`) was scoped to upstream drift only, and was itself removed for being unused (zero executions ever) rather than widened
5. Quality validation was never treated as its own cross-layer concern separate from any one command's own scope

**Root cause:** Quality validation has never been treated as a first-class, cross-layer concern; the one prior attempt was narrowly scoped and has since been removed rather than replaced.

**Affected files:**
- `edgar_warehouse/silver_store.py` — `get_table_counts()` exists but is unused in CI/gates
- `tests/` — no cross-layer consistency tests

---

## Issue 12 — Manifest fragmentation: 5+ manifest files per run, no consolidated view

**Observation:** Each command writes bronze/staging/silver/gold/artifacts manifests independently.

**5-Whys:**
1. Each layer emits its own manifest with layer-specific metadata
2. Manifests are consumed by different systems (staging loaders, Snowflake, monitoring)
3. There was no requirement for a unified run manifest
4. Each manifest was added when a specific consumer needed it
5. No run-level lineage was ever centralized

**Root cause:** Per-layer manifests serve different consumers but there's no run-level manifest that ties all produced artifacts together with lineage.

**Affected files:**
- `edgar_warehouse/infrastructure/run_manifest_builder.py` — per-layer manifest construction
- `edgar_warehouse/config/warehouse_paths.properties` — `manifest.default.*` paths
- `edgar_warehouse/infrastructure/dataset_path_catalog.py` — `planned_manifest_paths()` per command
