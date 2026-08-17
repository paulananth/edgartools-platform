# Decide the Local Dev/Test Replacement Strategy

Type: grilling
Status: resolved

## Question

Per this map's charting decision ("everywhere — DuckDB leaves the codebase
entirely"), the test suite's current fixture strategy goes away too: a
large number of unit tests build real `SilverDatabase`-backed DuckDB
instances directly (e.g. `tests/unit/test_bronze_recovery_no_db_row.py`,
`test_gold_models_streaming.py`, `test_sharding.py`, and — per this
session's own precedent in CLAUDE.md's "INSTITUTIONAL_HOLDS/EMPLOYED_BY"
5-whys — a hand-rolled stub was explicitly rejected in favor of "a real
`SilverDatabase`-backed DuckDB file" for exactly this kind of schema-
sensitive test). Removing DuckDB removes the cheap, fast, in-process
database those tests rely on.

Options to weigh (not exhaustive — this is a grilling ticket, not a
pre-decided menu): a real Snowflake test schema/account reachable from
CI (cost, credential provisioning, network dependency, speed); a different
local-first SQL engine as a stand-in (e.g. SQLite/Postgres-in-Docker) that
isn't literally DuckDB but still isn't Snowflake, and whether that
satisfies "DuckDB leaves the codebase" or just relocates the same
tradeoff; mocking/stubbing at a level where schema drift can't hide (the
same "hand-rolled stub drifted from real schema" failure mode CLAUDE.md
already documents as a real incident, cutting against a naive mock-based
answer). Also decide: does this apply uniformly to every current DuckDB-
backed test, or do some categories (e.g. tests specifically characterizing
DuckDB-specific behavior that's being deleted anyway) simply get deleted
rather than ported?

First step before deciding: grep `tests/` for `SilverDatabase(`,
`duckdb.connect(`, and `.duckdb` fixture paths to get a real inventory
count — don't estimate blast radius, measure it.

## Deliverable

A decided replacement fixture strategy, plus an inventory of how many
existing tests it affects and whether any category gets deleted instead of
ported.

## Answer

### Inventory (measured, not estimated)

`grep -rl` across `tests/` for `SilverDatabase(`, `duckdb.connect(`, and
`.duckdb` fixture paths: **56 of 186 test files (30%)** — 42 `tests/unit/`,
7 `tests/application/`, 4 `tests/mdm/`, 3 `tests/architecture/`. No file
imports `duckdb` outside this set (cross-checked separately).

That raw count overstates the real decision surface. Categorizing each file
by its actual target module splits it three ways:

1. **~8 files need no SQL engine at all** — `test_object_storage_conditional_promotion.py`,
   `test_object_storage_download_file.py`, `test_object_storage_stage_and_promote.py`,
   `test_publish_shard_if_remote.py`, `test_path_registry.py`,
   `test_bronze_recovery_no_db_row.py`, and the 2 architecture tests
   (`test_daily_identity_refresh_state_machine.py`,
   `test_load_history_state_machine.py`). These test S3 staging/promotion
   mechanics (ETag guards, conditional writes) where `.duckdb`/`silver.duckdb`
   is only an example blob being moved through object storage — they'll
   point at whatever object type Ticket 01's write path actually promotes
   (almost certainly Parquet), independent of this ticket's answer.
2. **~5-6 files retire outright, logic moves to dbt SQL** —
   `test_gold_models_streaming.py`, `test_gold_models_financial_derived.py`,
   `test_gold_models_financial_fact.py`, `test_gold_manifest_tracking.py`,
   `test_silver_protection_merge_chunking.py`,
   `test_silver_store_schema_migration.py`. These characterize Python-side
   Gold building and merge-conflict resolution that the already-decided
   target architecture retires in favor of dbt's SQL-side latest-wins
   collapse (`gold_models.py`'s Python builders, per the closed
   silver-snowflake-migration map's Ticket 03). Where dbt's own
   `unit_tests:` framework (already live for 4 gold models) can express the
   same check, it replaces the deleted Python test; it needs a real
   Snowflake connection to run (not free/offline), so it doesn't change the
   local-substrate question below, only narrows how much falls to Python.
3. **~4 files test MDM-reads-Silver via `ShardedSilverReader`** —
   `test_sharding.py`, `test_silver_reader_monolith_fallback.py`,
   `test_adv_preflight.py`, `test_source_to_mdm_load_path.py`. Retiring per
   Ticket 02 (blocked, not this ticket) — they get rewritten against
   whatever Ticket 02 picks as MDM's replacement read path, not against a
   local Silver stand-in at all.
4. **The remaining ~35-38 files are the actual decision** — operational
   bookkeeping that has to live *somewhere* queryable and fast: the
   `sec_fetch_active` lease, discovery/pipeline-run checkpoints,
   "has this window already published" idempotency gates
   (`test_windowing.py`, `test_skip_noop_silver_publish.py`), seed-universe's
   tracking-status safety-net guard (confirmed still load-bearing by the
   already-resolved `seed-universe-narrow-hydrate` map's Ticket 05 — MDM
   becoming system-of-record for novelty detection did *not* eliminate the
   local existence check; it stayed the correctness backstop against MDM's
   one-run staleness window), and the new landing-zone export write path
   itself (`test_silver_landing_export.py`). None of this is SEC filing
   content or MDM golden-record data — it's warehouse-run coordination
   state that doesn't live in MDM or Snowflake gold.

### Why a real SQL engine at all for that remainder — not a dict, not JSON

This bookkeeping isn't simple key-value state; the actual behavior under
test is genuine relational logic — composite/indexed keys (accession_number
+ owner_index + txn_index), uniqueness constraints, and `ON CONFLICT ...
DO UPDATE` upsert semantics with real overwrite hazards. That last point
isn't hypothetical: the `seed-universe-narrow-hydrate` map's own Ticket 05
found a live one — `upsert_company_sync_state`'s
`ON CONFLICT (cik) DO UPDATE SET tracking_status = excluded.tracking_status`
unconditionally overwrites on conflict, which would silently reactivate a
paused or completed company if its guard were ever wrong. A test only
catches a bug like that if it runs against something that actually resolves
`ON CONFLICT` the way production SQL does. A Python dict or JSON file
standing in for the database wouldn't reproduce that failure mode at all —
it's the same "hand-rolled stub drifted from real schema" risk CLAUDE.md
already documents as a real, costly incident (INSTITUTIONAL_HOLDS/
EMPLOYED_BY), not a new concern invented for this ticket.

### Why SQLite specifically, once "a real SQL engine" is settled

- **Not real Snowflake in CI**: blocked today independent of cost/speed —
  Snowflake DEV was decommissioned 2026-07-29 per CLAUDE.md; there is
  currently no non-prod Snowflake environment to target, and standing one
  up is a prerequisite this ticket shouldn't absorb.
- **Not Postgres-in-Docker**: adds container-startup latency and a
  Docker-availability dependency to every test run, for no evidence any of
  the ~35-38 files need a Postgres-specific feature SQLite lacks.
- **Not mocking/stubbing**: the exact rejected pattern above.
- **SQLite, plain stdlib `sqlite3`, no ORM**: zero new dependency, in-process
  (no network, no container), and dialect-checked directly against
  `silver_store.py`/`silver_protection.py`'s actual SQL — no DuckDB-specific
  column types in the schema; `ON CONFLICT` (53 occurrences) is standard
  SQLite syntax unchanged since 3.24; the one real gap is `QUALIFY
  ROW_NUMBER() OVER (...)` (13 occurrences, all in `silver_store.py`), a
  DuckDB/Snowflake-dialect shorthand SQLite doesn't have, needing a
  mechanical rewrite to a `WHERE rn = 1` subquery/CTE. That's real, sizeable
  work — not a free swap — but it's the only dialect gap found; no
  `PIVOT`/`EXCLUDE`/`GROUP BY ALL`/DuckDB-only functions appear anywhere in
  either file.
- **No SQLAlchemy.** Checked directly: `silver_store.py`/`silver_protection.py`/
  `silver_support/*.py` never import `sqlalchemy` — that library is used
  exclusively inside `edgar_warehouse/mdm/**` for MDM's own Postgres ORM,
  and not even MDM's Snowflake writer uses it there (it calls
  `snowflake.connector` directly). Silver's target Snowflake write path
  won't be SQLAlchemy-based either. Tying this ticket's fixture strategy to
  Ticket 06's schema-representation choice (SQLAlchemy models vs. raw SQL)
  was an earlier framing error in this same grilling session — corrected:
  this ticket's SQLite answer is independent of Ticket 06.

### Deliverable

- **Delete, don't port**: the ~8 object-storage-only files (repoint at the
  real post-cutover object type when Ticket 01 lands, not part of this
  ticket) and the ~5-6 dbt-superseded files.
- **Rewrite against Ticket 02's actual replacement, not this ticket's
  answer**: the ~4 `ShardedSilverReader`-reading MDM files.
- **Port to plain SQLite (stdlib, no ORM)**: the remaining ~35-38 files,
  after mechanically rewriting the 13 `QUALIFY` clauses in
  `silver_store.py` to portable `WHERE rn = 1` form.
