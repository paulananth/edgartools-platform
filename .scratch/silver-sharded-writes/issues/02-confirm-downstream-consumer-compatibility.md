# Confirm Downstream Consumer Compatibility With N Shards

Type: research
Status: resolved
Blocked by: none

## Question

Once `load_history`/`daily_incremental`/`bootstrap` write via shards instead
of one canonical file, what breaks for the code that currently assumes a
monolith?

1. `gold-refresh` reads the full dataset — does it already go through
   `ShardedSilverReader` (which already unions N shard files), or does it
   read `silver.duckdb` directly? Cite the exact call site
   (`edgar_warehouse/serving/gold_models.py` and/or
   `warehouse_orchestrator.py`'s gold-refresh path).
2. `ShardedSilverReader` (`edgar_warehouse/silver_support/sharded_reader.py`)
   — is its shard count (currently 4: `shard-{0..3}.duckdb`) hardcoded
   anywhere, or does it discover shards dynamically? If a primary command's
   first sharded write needs a different shard count than 4, what has to
   change?
3. Any other direct reader of `silver.duckdb` by path (ad-hoc/debug tooling,
   `validate_data_quality.py`'s `build_gold()` caller mentioned in
   CLAUDE.md's gold-build-memory 5-whys, migration scripts) — enumerate them
   via a repo-wide grep for the canonical path pattern and state whether
   each already works against `ShardedSilverReader` or would need
   migrating too.
4. Does the canonical *monolith* file need to keep existing at all once
   primary commands write shards (e.g. as a compatibility artifact for
   anything not yet updated), or can it be retired once every consumer is
   confirmed shard-compatible?

## Deliverable

Answer inline in this ticket's resolution comment — cite every claim to a
`file:line` reference. If the investigation is large, a findings file under
`.scratch/silver-sharded-writes/research/` is fine.

## Answer

Full detail with every citation:
[`research/02-downstream-consumer-compatibility.md`](../research/02-downstream-consumer-compatibility.md).
Summary:

1. **gold-refresh does NOT go through `ShardedSilverReader` today** — and neither does any other
   `GOLD_AFFECTING_COMMANDS` member (`warehouse_orchestrator.py:85-95`:
   `bootstrap-full`/`bootstrap-next`/`bootstrap`/`daily-incremental`/`targeted-resync`/
   `full-reconcile`/`gold-refresh`). The shard-routing gate
   (`warehouse_orchestrator.py:498-503`) is `command_name == "bootstrap-batch" and
   context.storage_root.is_remote and bool(arguments.get("cik_list"))` — true only for
   `bootstrap-batch`. Every other command falls to `_open_silver_database` →
   `open_silver_database` (`silver_support/session.py:13-18`), which opens the monolith
   `silver/sec/silver.duckdb` as a `SilverDatabase`. `iter_gold_tables(db)`/`build_gold(db)`
   (`serving/gold_models.py:1283-1308`) duck-type on either `SilverDatabase` or
   `ShardedSilverReader`, so the *interface* is shard-ready, but the object actually constructed
   is the monolith. `_hydrate_all_shards`'s docstring claiming it's "used by gold-refresh"
   (`warehouse_orchestrator.py:1261`) is stale — its only real caller is MDM's
   `_silver_reader()` (`mdm/cli.py:591`). Complication: gold-refresh's `db` is also the writable
   target for `start_sync_run`/`start_pipeline_run`/`record_gold_manifest`/`complete_sync_run`
   (lines 564, 587, 677, 715) — `ShardedSilverReader` is read-only with no such methods, so
   fixing this is a small design decision (separate bookkeeping writer), not a one-line reader
   swap.
2. **Shard count is not hardcoded in any runtime path** — `ShardedSilverReader.__init__` takes
   an arbitrary-length `shard_paths: list[str]` (`sharded_reader.py:101-132`), and
   `shard_manifest.py`/`_hydrate_all_shards`/`_shard_partition_ciks`
   (`warehouse_orchestrator.py:1258-1273`, `5136-5165`) all read `manifest["shard_count"]`
   dynamically. The one real hardcode is in the one-time conversion tool,
   `migrate_silver_shards.py:171-174` (`if len(bands) != 4: raise ...`) plus its docstring/
   `DEFAULT_BANDS`. A different shard count needs no runtime code change — only that script's
   check and a freshly generated manifest. Flagged for ticket 06 to build on.
3. Enumerated every non-test direct reader of the monolith path: `validate_data_quality.py:92`
   (also calls `build_gold(db)` for its `gold_vs_silver` check — same fix needed as gold-refresh,
   plus reads `pipeline_run` directly), `verify_pipeline_run.py:58-61` (`db.get_pipeline_run`),
   and five `scripts/ops/*.py` debug tools (`diagnose-mdm-run.py`, `check-issued-by-coverage.py`,
   `check-neo4j-e2e.py`, `diagnose-silver-anomalies.py`, `verify-counts.py`) that each download
   a hardcoded `s3://.../warehouse/silver/sec/silver.duckdb` and `duckdb.connect()` it directly —
   none are shard-aware, and none would error if the monolith went stale, they'd just silently
   read old data. Also found a bookkeeping-table gap: `pipeline_run`/`gold_manifest`/
   `discovery_checkpoint`/`pipeline_run_lease`/`schema_migration` (`silver_store.py:34-503`) are
   not in `ShardedSilverReader._TABLES` at all — and arguably shouldn't be naively unioned even
   if added, since a `pipeline_run` row belongs to one specific shard/run, not the whole universe.
   Separately flagged (not a read-compat issue, but adjacent): `bootstrap_fundamentals.py:135`
   (Stage 1B fundamentals writer, `load_history`'s `FetchEntityFacts`/etc.) writes the monolith
   directly and is never routed through the shard gate at all — a fourth primary-write surface
   the map's Destination doesn't name.
4. **Best-supported answer: the monolith cannot be retired the moment primary commands write
   shards** — every consumer in 1 and 3 reads it directly today with no shard fallback, and the
   five ops scripts in particular would silently serve stale data with no error signal if writes
   stopped. Recommend either (a) primary commands dual-write (shards + monolith merge) until every
   consumer above is migrated, or (b) migrate every consumer first, accepting gold-refresh's
   bookkeeping-write redesign, before primary commands stop writing the monolith. Which of these
   is preferred is a rollout-sequencing decision for ticket 05, not resolved here.
