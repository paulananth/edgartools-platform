# Pipeline throughput architecture

## Destination

A locked architecture decision for how to meaningfully cut the wall-clock
duration of the `daily_incremental`, `load_history`, `bootstrap`, and
`gold_refresh` Step Functions pipelines (`edgar_warehouse/application/
warehouse_orchestrator.py` + `edgar_warehouse/silver_protection.py`) --
covering the concurrency model (within-task and across-ECS-task) and the
silver-merge storage path. Done when there is a written, evidence-backed
decision on each of those axes that someone can implement without further
architecture debate. This map does not implement the decision itself --
same split as [release-readiness](../release-readiness/map.md), which
executes the micro-fixes this map's evidence builds on.

## Notes

- Domain: `edgar_warehouse/application/warehouse_orchestrator.py` (pipeline
  orchestration, per-CIK loops), `edgar_warehouse/silver_protection.py`
  (canonical silver merge/promotion), `edgar_warehouse/infrastructure/
  object_storage.py` (S3), ECS task defs + Step Functions state machines in
  `infra/scripts/deploy-aws-application.sh`.
- [release-readiness](../release-readiness/map.md) tickets 67-72 already
  fixed five *instances* of the same shape (unbatched per-row DB loops,
  a cold boto3 client per call, redundant S3 re-downloads, per-file
  `shutil.copy2`) one at a time as they were discovered live. That map's
  ticket 73 explicitly flagged this recurring pattern as "worth a closer
  look later" -- this map is that closer look, aimed at the pattern instead
  of the next instance of it. Treat those six fixes as evidence inputs, not
  as re-open candidates.
- Consult `/gof-refactor-reviewer` before any ticket that proposes
  restructuring `silver_protection.py` or the orchestrator's per-CIK loops
  -- a review of `reduce_identity_refresh` and
  `merge_candidate_into_canonical` was run earlier this session but its
  findings were lost to context compaction before being written down;
  re-run it and this time land the findings on the relevant ticket as an
  asset.
- Standing preference from this session: every fix ships with real
  measurements against real data/infra (row counts, live timings), not
  estimates -- keep that discipline for this map's tickets too.
- Mode: decision-spec only (wayfinder default, not overridden) --
  resolving a ticket here means writing down the decision, not shipping
  code. Implementation is a normal follow-up pass once the map is clear.

## Decisions so far

(none yet)

## Not yet specified

- Whether the underlying storage model -- one DuckDB file per silver
  shard, mutated via full-file copy + reattach -- is still the right
  primitive at current/projected data scale (1GB+ canonical file today),
  or whether pipeline speed ultimately requires moving off it entirely.
  Too large to ticket before [Profile the real bottleneck breakdown across
  pipeline stages](issues/01-profile-pipeline-stage-bottleneck-breakdown.md)
  shows whether storage I/O is actually the dominant cost.
- Whether ECS task memory/CPU sizing itself (as opposed to task *count* or
  intra-task concurrency) is a limiting factor -- folded into ticket 01's
  profiling pass rather than ticketed separately for now.

## Out of scope

- MDM / graph-sync stages (`mdm-run`, `mdm-backfill-relationships`,
  `mdm-sync-graph`) -- explicitly excluded when scoping this map; they run
  on a separate Postgres+graph path with their own cost model. A future
  map can cover them if warranted.
- Carrying execution into this map (each ticket only decides; no ticket
  ships code) -- explicit choice when charting, matching this map's
  Destination.
