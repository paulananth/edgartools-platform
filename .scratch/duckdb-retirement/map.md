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

<!-- none yet -- map just charted -->

## Not yet specified

(none yet — breadth-first frontier below covers everything surfaced during
charting; new fog may surface as tickets resolve)

## Out of scope

<!-- none yet -->
