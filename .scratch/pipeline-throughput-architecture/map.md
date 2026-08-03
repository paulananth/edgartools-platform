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

1. [Research SEC rate-limit headroom](issues/02-research-sec-rate-limit-headroom.md) — SEC's published ceiling is a flat 10 req/sec with no burst allowance, framed per-operator "regardless of machines used" (10-min cooldown on violation); the in-process limiter is a hardcoded 9 req/sec/task (no env override); prod's `network_runtime` Terraform module has no NAT gateway at all -- ECS tasks run in public subnets with `AssignPublicIp: ENABLED`, so concurrent tasks get distinct public IPs, not a shared NAT IP.
2. [Profile the real pipeline stage bottleneck breakdown](issues/01-profile-pipeline-stage-bottleneck-breakdown.md) — resolved for `daily-incremental` from real timestamps (a fully-cold-cache attempt, 209.5 min total): artifact-fetch loop dominates at 57.5% (119.4 min, post-tickets-69/70-fix), submissions bronze-capture 23.3% (48.3 min), silver apply 16.3% (33.9 min, ~1,175 rows/sec — scales with volume, not pathological), resume/repair existence-checks 2.5% (5.1 min — a new small unbatched-per-row finding, filed separately as release-readiness ticket 75). Critically: the artifact loop runs at only 4.27 fetches/sec, well under the 9-10 req/sec rate-limit ceiling — **not rate-limit-bound today**, real headroom exists before concurrency would even contend with SEC's limit. `load_history`/`bootstrap-batch` not profiled this session — left as a gap in Not yet specified. Unblocked tickets 03, 04, 05.
3. [Decide intra-task concurrency model](issues/03-decide-intra-task-concurrency-model.md) — resolved (grilling): yes, pursue it, scoped to the artifact-fetch loop only (submissions bronze-capture deferred as a fast-follow). `ThreadPoolExecutor`, not asyncio (blocking I/O work, zero existing asyncio precedent, `sec_client.py` already sync). DB writes stay serialized on the main thread (DuckDB single-connection safety). Worker bound: 5, matching the existing `BOOTSTRAP_BATCH_CONCURRENCY` convention; `pyrate_limiter`'s `Limiter` confirmed thread-safe (internal `RLock`) so it remains the real throughput ceiling regardless of pool size. Full 5-part test plan specified (equivalence, rate-limiter compliance, DB-write-serialization, partial-failure equivalence, live measurement). Flagged, not decided: the circuit breaker's "consecutive errors" semantics need redefining under out-of-order concurrent completion — left to implementation. Addendum: this decision's safety guarantee assumes no *other* SEC-fetching command runs concurrently — see ticket 09.
4. [Decide cross-task fan-out model](issues/04-decide-cross-task-fanout-model.md) — resolved (grilling): submissions-bronze-capture gets **no fan-out** — surfaced mid-grilling that this loop (`_capture_submission_bronze_snapshot`) is the *same shared function* used by `daily_incremental`, `bootstrap`, `bootstrap_full`, `targeted_resync`, **and** `bootstrap-batch`, so it inherits ticket 06's intra-task-concurrency fix instead of needing its own fan-out — one fix, five callers. `gold-refresh`'s fan-out question couldn't be answered responsibly (never profiled, real N-way-file-copy tradeoff) — split into ticket 07 (profile, unblocked) + ticket 08 (decide, blocked by 07) rather than guessed at.
5. [Decide silver-merge storage path](issues/05-decide-silver-merge-storage-path.md) — resolved (grilling + fresh `/gof-refactor-reviewer`): **leave it**. Real measured cost of the whole `ReduceIdentityRefresh` stage (4 candidates, `sec_thirteenf_holding`'s 6.8M rows among 21 protected tables per candidate): 187.9s total, ~1.4% of the run's ~225-min wall-clock — smaller than release-readiness ticket 75's 2.5%, which was already judged worth fixing. Reviewer confirmed the ticket's original hypothesis was stale: `_matching_canonical_rows_as_dicts` is already a targeted lookup (not a full scan, fixed in an earlier commit for OOM), and the per-row insert/update loop only touches the anti-join-filtered delta (hundreds of rows), not full tables. `git log` showed 5+ correctness-driven fixes on this exact path — real fragility that raises restructuring's regression cost well above a ~1.4% gain. One real, cheap, separate finding split off: `reduce_identity_refresh` double-fetches every reference/delta object from S3 (verify-then-discard, then re-fetch) — filed as release-readiness ticket 76.
6. [Fix cross-task SEC rate-limit compliance](issues/06-fix-cross-task-sec-rate-limit-compliance.md) — resolved as a decision: `bootstrap-batch`'s existing `BOOTSTRAP_BATCH_CONCURRENCY=3` fan-out risks up to 27 req/sec aggregate against SEC's stated 10 req/sec ceiling (live in prod today). Fix via the same intra-task `ThreadPoolExecutor` pattern as ticket 03, applied to `_capture_submission_bronze_snapshot` — confirmed as a **shared function** across `daily_incremental`/`bootstrap`/`bootstrap_full`/`targeted_resync`/`bootstrap_batch`, so one fix covers all five and also resolves ticket 04's deferred submissions-bronze-capture question. Not fixed via concurrency tuning (the per-task limiter is a hardcoded literal, so the only compliant task-count fix would eliminate the fan-out entirely). Implementation split to [release-readiness ticket 78](../../release-readiness/issues/78-implement-shared-submissions-fetch-concurrency.md) (and ticket 03's own implementation gap filed alongside as [release-readiness ticket 77](../../release-readiness/issues/77-implement-artifact-fetch-concurrency.md)) — this map stays decision-only.

7. [Profile gold-refresh stage breakdown](issues/07-profile-gold-refresh-stage-breakdown.md) — resolved: triggered a fresh run (both historical runs predated current fixes and their logs had expired). Breakdown of 169.12s total: silver DB hydration 8.2% (13.78s), setup gaps 4.5%, gold table build (27 tables) 33.0% (55.77s), **silver merge/publish (unconditional) 35.9% (60.65s) — the single largest cost, and structurally zero-effect, not just unchanged-this-run**: traced the merge mechanics — `gold-refresh` only reads `PROTECTED_TABLE_REGISTRY` business tables (never writes them), and its only local writes (`pipeline_run`/`sec_sync_run`) are `EXCLUDED_OPERATIONAL_TABLES`, which the merge loop never pulls from the candidate at all (output starts as a copy of canonical, excluded tables pass through untouched). Zero bytes of real content move on any run, by construction — confirms the user's stated one-directional requirement (silver → gold/MDM/neo4j) is already true in substance; the step is pure waste, not a safety mechanism earning its cost. Split off as [ticket 10](issues/10-decide-gold-refresh-unconditional-silver-republish.md) (grilling — narrowed to whether anything else depends on this step running, before recommending skipping it outright for gold-refresh). Unblocks ticket 08 (fan-out) using the 55.77s/27-table build breakdown, though 08's cost/benefit should be re-evaluated once ticket 10 resolves — likely a much bigger win on its own than fan-out.

10. [Decide gold-refresh's unconditional silver republish](issues/10-decide-gold-refresh-unconditional-silver-republish.md) — resolved (grilling): skip it. Confirmed nothing depends on it (no S3 event notifications on the silver.duckdb key, no consumer of `pipeline_run`/`sec_sync_run` or the `silver_database` write-entry anywhere in the repo). Scoped as a **general rule** (any command whose candidate never actually changed a `PROTECTED_TABLE_REGISTRY` table skips publish), via **dynamic runtime detection**, not a static command allowlist — explicitly rejected the allowlist approach given its silent-data-loss risk if a command later gains real writes. Must check only protected tables, not the whole local file (excluded operational bookkeeping writes on every run would defeat a naive whole-file check). Implementation split to [release-readiness ticket 79](../../release-readiness/issues/79-implement-skip-noop-silver-publish.md).

8. [Decide gold-refresh fan-out](issues/08-decide-gold-refresh-fanout.md) — resolved (grilling): **no fan-out**. Modeled with ticket 07's real numbers adjusted for ticket 10's fix: post-fix baseline ~108.5s, of which ~52.7s (hydration + setup + container overhead) is fixed per task and doesn't shrink with more tasks — only the 55.77s table build divides. Best realistic case (~N=4-6) is ~39-43% faster (~62-67s), before accounting for real ECS/Fargate task-launch latency eating into that further. Real but modest savings against genuine new complexity (Distributed Map, per-task hydration, N-way partial-output reconciliation) for a command that was never the actual bottleneck this map exists to fix.

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
- `load_history`/`bootstrap-batch`'s own *non-SEC-fetch* stage-by-stage
  breakdown (its per-batch parse/write/silver-merge costs, as opposed to
  the SEC-fetch loop ticket 06 already covers) -- still unprofiled. Lower
  priority since `bootstrap-batch` already has fan-out parallelism for
  whatever this breakdown would reveal.

## Out of scope

- MDM / graph-sync stages (`mdm-run`, `mdm-backfill-relationships`,
  `mdm-sync-graph`) -- explicitly excluded when scoping this map; they run
  on a separate Postgres+graph path with their own cost model. A future
  map can cover them if warranted.
- Carrying execution into this map (each ticket only decides; no ticket
  ships code) -- explicit choice when charting, matching this map's
  Destination.
