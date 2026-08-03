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

- [Research SEC rate-limit headroom](issues/02-research-sec-rate-limit-headroom.md) — SEC's published ceiling is a flat 10 req/sec with no burst allowance, framed per-operator "regardless of machines used" (10-min cooldown on violation); the in-process limiter is a hardcoded 9 req/sec/task (no env override); prod's `network_runtime` Terraform module has no NAT gateway at all -- ECS tasks run in public subnets with `AssignPublicIp: ENABLED`, so concurrent tasks get distinct public IPs, not a shared NAT IP.
- [Decide intra-task concurrency model](issues/03-decide-intra-task-concurrency-model.md) — resolved (grilling): yes, pursue it, scoped to the artifact-fetch loop only (submissions bronze-capture deferred as a fast-follow). `ThreadPoolExecutor`, not asyncio (blocking I/O work, zero existing asyncio precedent, `sec_client.py` already sync). DB writes stay serialized on the main thread (DuckDB single-connection safety). Worker bound: 5, matching the existing `BOOTSTRAP_BATCH_CONCURRENCY` convention; `pyrate_limiter`'s `Limiter` confirmed thread-safe (internal `RLock`) so it remains the real throughput ceiling regardless of pool size. Full 5-part test plan specified (equivalence, rate-limiter compliance, DB-write-serialization, partial-failure equivalence, live measurement). Flagged, not decided: the circuit breaker's "consecutive errors" semantics need redefining under out-of-order concurrent completion — left to implementation.
- [Profile the real pipeline stage bottleneck breakdown](issues/01-profile-pipeline-stage-bottleneck-breakdown.md) — resolved for `daily-incremental` from real timestamps (a fully-cold-cache attempt, 209.5 min total): artifact-fetch loop dominates at 57.5% (119.4 min, post-tickets-69/70-fix), submissions bronze-capture 23.3% (48.3 min), silver apply 16.3% (33.9 min, ~1,175 rows/sec — scales with volume, not pathological), resume/repair existence-checks 2.5% (5.1 min — a new small unbatched-per-row finding, filed separately as release-readiness ticket 75). Critically: the artifact loop runs at only 4.27 fetches/sec, well under the 9-10 req/sec rate-limit ceiling — **not rate-limit-bound today**, real headroom exists before concurrency would even contend with SEC's limit. `load_history`/`bootstrap-batch` not profiled this session — left as a gap in Not yet specified. Unblocks tickets 03, 04, 05.

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
  profiling pass rather than ticketed separately for now. Ticket 01's
  resolution found no evidence of CPU/memory throttling (no OOM, no visible
  stalls) but did not pull Container Insights metrics directly -- still
  genuinely unmeasured.
- `load_history`/`bootstrap-batch`'s own stage-by-stage breakdown -- ticket
  01 profiled `daily-incremental` only (the pipeline that was actually
  running live during this investigation); `load_history` already has
  fan-out parallelism via `bootstrap-batch` xN, so it's a lower-priority gap,
  but tickets 03/04's decisions should stay scoped to what ticket 01 actually
  measured until this is filled in.

## Out of scope

- MDM / graph-sync stages (`mdm-run`, `mdm-backfill-relationships`,
  `mdm-sync-graph`) -- explicitly excluded when scoping this map; they run
  on a separate Postgres+graph path with their own cost model. A future
  map can cover them if warranted.
- Carrying execution into this map (each ticket only decides; no ticket
  ships code) -- explicit choice when charting, matching this map's
  Destination.
