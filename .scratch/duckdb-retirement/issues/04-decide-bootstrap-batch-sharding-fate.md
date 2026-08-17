# Decide bootstrap-batch's Sharding Mechanism Fate

Type: grilling
Status: resolved
Blocked by: 07 (resolved)

## Question

`bootstrap-batch` (run by `edgartools-prod-silver-mdm-gold`'s `BatchSilver`
Map, `MaxConcurrency=3`, always with `--artifact-policy skip` per CLAUDE.md's
key invariants) has its own working, measured, tested CIK-sharded
hydrate/publish mechanism — `pipeline-throughput-architecture`'s Ticket 12,
a real 76s→3.2s per-batch optimization. The closed silver-snowflake-
migration map's Ticket 06 flagged this as "likely obsolete once silver
lives natively in Snowflake (no more local monolith/shard split to reason
about at all), but not yet confirmed." This map's charting grilling
confirmed it's in scope here.

Decide: does `bootstrap-batch` simply start calling the same shared
`_run_submissions_bronze_then_silver` write site the other four commands
use (per this map's assumed target: parse writes only to the Snowflake
landing zone), eliminating the sharded hydrate/publish mechanism entirely?
Given `bootstrap-batch` is explicitly a *reprocessing* pipeline over
already-loaded bronze (not new SEC fetches) — does re-emitting already-
resolved rows into an append-only landing zone even do useful work, given
dbt's latest-`parse_sequence`-wins collapse would just dedupe them away?
If bootstrap-batch's actual purpose (re-deriving silver rows from bronze
after a parser/logic fix, without new SEC calls) still has value under the
new architecture, what does it look like — does it become a targeted
`INSERT ... SELECT`-style landing-zone reprocessing pass instead of a
local DuckDB rebuild? What happens to `MaxConcurrency=3` once shard
ownership (the thing that made concurrency safe) no longer exists as a
concept?

## Deliverable

A decided fate for `bootstrap-batch`'s current sharding mechanism and
what (if anything) replaces its reprocessing capability under a
DuckDB-free architecture.

## Answer

**Grounding, checked directly:** `bootstrap-batch` already dual-writes today
— every run both hydrates/opens one CIK-range shard file (`open_silver_shard`,
`_hydrate_shard_for_window`, `warehouse_orchestrator.py:499-566`) *and* emits
parsed rows to the Snowflake landing zone via the same `landing_export`
buffer the other 4 commands use (`silver_landing_writer.py`). The landing
zone write is **not** a shared mutable object at all — every write is its own
`{table}/business_date=.../run_id=.../{table}.parquet` file (confirmed by
reading `write_landing_export`), so it carries none of the write-contention
problem the shard mechanism exists to solve. Confirmed via
`deploy-aws-application.sh`'s own comment (`write_bronze_seed_silver_gold_definition`)
that `bootstrap-batch`'s reprocessing read path is **bronze-driven, not
silver-dependent** — it reads already-captured bronze bytes from S3 and
re-parses them; it does not need existing shard content to do its job
correctly. Separately, this session's own pipeline-resumability work
(BatchSilver default-path/release-mode done markers,
`write_default_batch_done_marker`/`batch_done_marker_path`) already replaced
shard-content-based resumability with S3 marker objects — another sign the
shard file's remaining job is purely "somewhere to merge rows into," not
anything read-dependent.

- **The sharded hydrate/publish mechanism retires entirely.** Once Ticket 01
  (write-path cutover sequence — still open, but its already-assumed target
  is parse-writes-to-landing-zone-only) lands, `bootstrap-batch` drops the
  shard hydrate/open/publish calls and calls the exact same
  `_run_submissions_bronze_then_silver` write site the other 4 commands use,
  writing only to the landing zone. No DuckDB file, local or sharded,
  survives in this command's execution at all.
- **Reprocessing still does useful work — this was a real risk worth
  checking, not assumed.** dbt's latest-`parse_sequence`-wins collapse
  dedupes *identical* re-emissions, but a `bootstrap-batch` re-run exists
  specifically because a parser/logic fix shipped — its output for the same
  business key genuinely differs from the original parse, and lands with a
  strictly greater `parse_sequence`. The append-only landing zone plus
  latest-wins collapse is exactly the mechanism that makes that correction
  visible in gold, not a mechanism that would erase it. No `INSERT ...
  SELECT`-style SQL reprocessing pass is needed — `bootstrap-batch` stays
  the same shape it already is (a Python ECS task that reads bronze, re-runs
  the parser, emits Parquet to the landing zone), just lighter, since it
  drops the shard I/O it currently also does on every run.
- **`MaxConcurrency` is no longer bounded by write contention at all** — the
  entire reason it was tuned down from 4 (retry-storm on a full monolith) to
  the shard-count-matched, then empirically up to 20
  (`pipeline-throughput-architecture`'s Ticket 12, `wh_medium_arn`,
  30-vCPU account quota as the actual ceiling hit at `MaxConcurrency=16` on
  `wh_large_arn`) was managing concurrent writers racing an ETag-guarded
  promote of a shared mutable shard file. With no shared object to promote,
  that constraint disappears; the practical ceiling becomes the Fargate
  vCPU quota (known: 30 vCPU) and Snowflake landing-zone ingestion
  throughput under many small concurrent Parquet writes (not yet measured
  for this specific write pattern — flagged as a real unknown, not assumed
  fine). This ticket does not pin an exact new number — that's an
  implementation-time tuning decision, consistent with how Ticket 12 itself
  resolved its own concurrency number empirically rather than by
  calculation.
- **Explicitly deferred, not decided here:** where `sec_company_sync_state`
  -equivalent bookkeeping (the tracking-status/checkpoint state some
  bootstrap-batch call sites, e.g. `silver_mdm_gold`'s, still read for
  resumability) lives once no DuckDB file exists anywhere to hold it. That's
  Ticket 01's scope (the general write-path storage question for all 5
  commands), not specific to bootstrap-batch's sharding fate.
- **Also explicitly deferred:** deleting the shared shard-file infrastructure
  itself (`shard-manifest.json`, `open_silver_shard`, `_hydrate_shard_for_window`,
  `band_for_cik`, `_shard_partition_ciks`, and the round-robin
  `_write_cik_universe_batches` interleave `pipeline-throughput-architecture`
  Ticket 12 built). That machinery is shared infrastructure touching
  `load_history`'s own read path too, not owned by `bootstrap-batch` alone —
  its removal belongs to Ticket 01's broader write-path cutover, once every
  DuckDB-touching command (not just this one) has moved off it. This ticket
  only decides that `bootstrap-batch` itself should stop being one of that
  mechanism's callers.
