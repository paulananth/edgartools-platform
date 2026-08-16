# Downstream Consumer Compatibility With N Shards — Findings

Supporting detail for
[`issues/02-confirm-downstream-consumer-compatibility.md`](../issues/02-confirm-downstream-consumer-compatibility.md).

## 1. gold-refresh's read path

**Finding: gold-refresh does NOT go through `ShardedSilverReader` today. It opens the monolith
`silver.duckdb` directly, and this is true of every `GOLD_AFFECTING_COMMANDS` member, not just
`gold-refresh`.**

- `GOLD_AFFECTING_COMMANDS` (`edgar_warehouse/application/warehouse_orchestrator.py:85-95`) = 
  `{bootstrap-full, bootstrap-next, bootstrap, daily-incremental, targeted-resync, full-reconcile,
  gold-refresh}`. All seven share one code path:
  `_execute_warehouse_bronze_capture` (`warehouse_orchestrator.py:472`).
- That function's shard-routing gate (`warehouse_orchestrator.py:498-503`):
  ```python
  _using_shard_path: bool = (
      command_name == "bootstrap-batch"
      and context.storage_root.is_remote
      and bool(arguments.get("cik_list"))
  )
  ```
  is `True` only for `bootstrap-batch`. For every `GOLD_AFFECTING_COMMANDS` member (including
  `gold-refresh`), `_using_shard_path` is always `False`, so execution falls to
  `warehouse_orchestrator.py:557-560`:
  ```python
  if not _using_shard_path:
      _hydrate_silver_database_from_storage(context)
      ...
      db = _open_silver_database(context.silver_root, landing_export=landing_export)
  ```
  `_open_silver_database` (`warehouse_orchestrator.py:982-985`) calls
  `open_silver_database` (`edgar_warehouse/silver_support/session.py:13-18`), which appends the
  canonical `silver/sec/silver.duckdb` suffix to the storage root and returns a `SilverDatabase`
  (`edgar_warehouse/silver_store.py`) — the monolith, not `ShardedSilverReader`.
- That same `db` is then handed to the gold build loop
  (`warehouse_orchestrator.py:640-690`): `for table_name, table in iter_gold_tables(db): ...`.
  `iter_gold_tables`/`build_gold` (`edgar_warehouse/serving/gold_models.py:1283-1308`) call
  `get_connection(db)`, which accepts `SilverDatabase` or `ShardedSilverReader` via duck typing
  (`._conn` attribute, per `sharded_reader.py:7-15`'s own docstring) — so the *interface* is
  shard-compatible, but the *object actually constructed for gold-refresh today* is the monolith
  reader, not the sharded one.
- **`_hydrate_all_shards` exists and its docstring claims "Used by gold-refresh and MDM commands
  that require the full silver dataset"** (`warehouse_orchestrator.py:1258-1261`) — but grepping
  every call site of `_hydrate_all_shards` shows it is called from exactly one place:
  `edgar_warehouse/mdm/cli.py:591` (MDM's `_silver_reader()`). Nothing in the gold-refresh path
  calls it. The docstring is aspirational/stale, not accurate as of this reading.
- **Complication for a naive fix:** the monolith `db` object gold-refresh opens is not read-only —
  it is also the target of bookkeeping writes in the *same* command run:
  `db.start_sync_run` / `db.start_pipeline_run` (`warehouse_orchestrator.py:564, 587`),
  `db.record_gold_manifest` (`warehouse_orchestrator.py:677`, writes the `gold_manifest` table),
  and `db.complete_sync_run` (`warehouse_orchestrator.py:715`). `ShardedSilverReader` is
  ATTACH'd `READ_ONLY` (`sharded_reader.py:32,107`) and has no write methods at all (only
  `.fetch()`/`.close()`, `sharded_reader.py:134-154`). So gold-refresh's `db` currently does
  double duty — data source for `iter_gold_tables()` *and* writable bookkeeping sink for
  `pipeline_run`/`sync_run`/`gold_manifest`. Swapping in `ShardedSilverReader` for the data-read
  role is not a drop-in replacement; a separate writable target for the bookkeeping role would be
  needed too.

## 2. Is the shard count hardcoded?

**Finding: `ShardedSilverReader` and every runtime shard-routing code path are shard-count-agnostic
(discover count from data). The ONE hardcode of "4" lives in the one-time migration script, not in
any runtime read/route path.**

- `edgar_warehouse/silver_support/sharded_reader.py` (157 lines, read in full): the constructor
  takes `shard_paths: list[str]` (line 101) — an arbitrary-length list — and loops over it
  (`for i, path in enumerate(shard_paths)`, line 105). Nothing in the file references a count of
  4, or any other literal shard count. Table exposure is also per-shard-dynamic: for each table in
  `_TABLES`, it probes every attached alias and unions only the aliases that actually have that
  table (lines 115-132) — so a mixed set of old/new-shape shards works too.
- `edgar_warehouse/application/sharding/shard_manifest.py`: `shard_count` is a required key
  read from the manifest JSON (`_REQUIRED_KEYS`, line 32) and used directly —
  `shards_for_window`/`band_for_cik` iterate `manifest["bands"]` (whatever length it is); nothing
  is hardcoded. The docstring's example manifest (lines 6-19) happens to show 4 bands, but that is
  documentation of a specific instance, not a code constraint.
- `warehouse_orchestrator.py`'s runtime callers are both dynamic:
  - `_hydrate_all_shards` (line 1258-1273): `for shard_index in range(manifest["shard_count"])`.
  - `_shard_partition_ciks` (line 5136-5165): `shard_count = int(manifest["shard_count"])`,
    builds `per_shard_ciks` of that length.
- **The actual hardcode:** `edgar_warehouse/application/commands/migrate_silver_shards.py` —
  docstring says "converts a monolithic silver.duckdb file into **four** CIK-range shard files"
  (line 4) and "replicated to ALL 4 shards" (line 14); `run_migration()` enforces it in code:
  ```python
  if len(bands) != 4:
      raise WarehouseRuntimeError(f"Expected exactly 4 bands, got {len(bands)}")
  ```
  (`migrate_silver_shards.py:171-174`). This is the **one-time monolith → shards conversion
  tool**, not a runtime read/write path.
- **What breaks if a primary command needs a different shard count than 4:** nothing in the
  runtime read path (`ShardedSilverReader`, `shard_manifest.py`, `_hydrate_all_shards`,
  `_shard_partition_ciks`) needs to change — they all take the count from the manifest. Only
  `migrate_silver_shards.py`'s hardcoded `!= 4` check (and its `DEFAULT_BANDS` constant, sized for
  4 bands) would need updating, and a fresh manifest with the new band boundaries would need to be
  generated and published. This is squarely ticket 06's ("Decide Shard-Count Growth Strategy")
  concern — flagging the exact hardcode location here for that ticket to build on, not resolving
  it in this ticket.

## 3. Other direct consumers of the monolith path

Repo-wide grep for `silver\.duckdb` / `open_silver_database(` outside `tests/`, the write path
(`silver_support/session.py`, `warehouse_orchestrator.py`, `migrate_silver_shards.py`,
`silver_protection.py`, `identity_refresh_publication.py`, `silver_event_reducer.py` — all part of
the canonical write/publish machinery, not standalone consumers) turned up:

| Caller | What it does | Shard-compatible today? |
|---|---|---|
| `edgar_warehouse/application/commands/validate_data_quality.py:91-103` | `open_silver_database(context.silver_root)` directly; calls `build_gold(db)` (line 230) for its `gold_vs_silver` check and `db.fetch("... FROM pipeline_run ...")` (line 154-163) for its row-count-monotonic check | **No.** Opens the monolith directly, same pattern as gold-refresh. This is the exact caller CLAUDE.md's gold-build-memory 5-whys names as needing `build_gold()`'s "random access across the full gold layer" — would need migrating in lockstep with gold-refresh's fix, plus its `pipeline_run` read has the bookkeeping-table gap below. |
| `edgar_warehouse/application/commands/verify_pipeline_run.py:58-59` | `open_silver_database(context.silver_root)`; `db.get_pipeline_run(run_id)` (line 61) | **No**, and worse than a simple read-path swap: `pipeline_run` is not one of `ShardedSilverReader._TABLES` (see gap below), so even routing this through `ShardedSilverReader` wouldn't expose the table it needs. |
| `scripts/ops/diagnose-mdm-run.py:66,93` | Downloads `s3://<bucket>/warehouse/silver/sec/silver.duckdb`, then `duckdb.connect(local_path, read_only=True)` | **No.** Ad-hoc debug script, hardcoded monolith S3 path. |
| `scripts/ops/check-issued-by-coverage.py:90,133` | Same pattern | **No.** |
| `scripts/ops/check-neo4j-e2e.py:81-88` | Same pattern | **No.** |
| `scripts/ops/diagnose-silver-anomalies.py:387-416` | Same pattern (`--silver-local` flag, defaults to a pre-downloaded monolith) | **No.** |
| `scripts/ops/verify-counts.py:84,97` | Same pattern | **No.** |
| `edgar_warehouse/application/commands/bootstrap_fundamentals.py:135,315` | `open_silver_database(context.silver_root)` — but as a **writer**, not a reader. This is the Stage 1B fundamentals command (`entity-facts`/`per-filing`/`thirteenf`/`company-identity` modes per its own docstring, lines 1-49) that `load_history`'s `FetchEntityFacts`/`FetchPerFilingFundamentals`/`FetchThirteenFHoldings` steps call. It has its own `open_silver_database` call and is never routed through `_execute_warehouse_bronze_capture`'s `_using_shard_path` gate at all. | **Not applicable to this ticket's read-compatibility question** (it's a write-path gap), but flagged because it means Stage 1B is a *fourth* primary-ingestion write surface (beyond `bootstrap-next`'s `WindowedBootstrap`, `daily_incremental`, `bootstrap`) that the parent map's Destination doesn't explicitly name and that also still targets the monolith unconditionally. Worth a note for ticket 01 or a new ticket, not resolved here. |

**Bookkeeping-table gap found while checking `verify_pipeline_run.py` and
`validate_data_quality.py`:** `edgar_warehouse/silver_store.py`'s `CREATE TABLE` list includes
`schema_migration` (34), `discovery_checkpoint` (374), `pipeline_run_lease` (392),
`pipeline_run` (480), and `gold_manifest` (503) — none of which appear in
`ShardedSilverReader._TABLES` (`sharded_reader.py:57-99`, which only lists `sec_*`/`stg_*` domain
tables). These are per-run/per-process control-plane tables, not universe data, so it's not
obviously correct to *union* them across shards the way domain tables are unioned even if they
were added to `_TABLES` — a `pipeline_run` row for a given `run_id` lives in whichever single
shard (or the monolith) that run actually wrote to, so "read across all shards" isn't the right
access pattern for it the way it is for `sec_company` et al. This is a design question the ticket
that migrates `validate_data_quality.py`/`verify_pipeline_run.py` will need to answer, not just a
missing-entry bug.

## 4. Does the monolith need to keep existing?

**Best-supported answer: it cannot be retired cleanly the moment primary commands start writing
shards — every consumer enumerated in §1 and §3 (gold-refresh and all six of its
`GOLD_AFFECTING_COMMANDS` siblings, `validate_data_quality.py`, `verify_pipeline_run.py`, and five
`scripts/ops/*.py` debug tools) reads it directly today, with no fallback to shards. Two
consequences follow directly from what was found, not from general caution:**

1. **The five `scripts/ops/*.py` tools are the sharpest risk.** They have no shard-awareness at
   all and no error path that would surface staleness — if primary commands stop updating the
   monolith, these scripts keep working and keep returning results, just against
   increasingly-stale data, with nothing indicating that's happening. This is a silent-staleness
   failure mode, not a crash — the same category of subtle correctness regression CLAUDE.md's
   "INSTITUTIONAL_HOLDS/EMPLOYED_BY" and "manifest-pipeline ownership" 5-whys warn about.
2. **`gold-refresh` (and its `GOLD_AFFECTING_COMMANDS` siblings) cannot simply be repointed at
   `ShardedSilverReader`** without also solving the bookkeeping-write problem from §1 (a read-only
   `ShardedSilverReader` has no `start_sync_run`/`record_gold_manifest`/`complete_sync_run`), so
   "just swap the reader" is not a one-line fix — it is itself a small design decision (separate
   writable bookkeeping target, or keep a thin per-run monolith/log purely for bookkeeping while
   sourcing gold-table SQL from shards).

**Given both of these, the monolith should stay alive (continue being written, not just left
stale) for a transition window** rather than being retired the moment primary commands start
writing shards. The two live options are: (a) primary commands dual-write — publish to shards
*and* still merge into the monolith — until every consumer above is migrated, or (b) migrate every
consumer above first (accepting the bookkeeping-write redesign for `GOLD_AFFECTING_COMMANDS`) and
only then have primary commands stop writing the monolith. Which of these is preferred is a
sequencing/rollout decision, not a fact this research ticket can resolve — it belongs with ticket
05 ("Decide Rollout Sequencing and Safety Gate"), which this finding directly informs.
