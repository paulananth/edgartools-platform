# Decoupled bronze pipeline

## Destination

A locked, evidence-backed architecture for a fully decoupled, message-driven
bronze-to-downstream pipeline: bronze capture becomes an independently-scaling
process that only writes bronze and emits an event; silver and gold become
independent, async, message-driven consumers of that event. Intended to fully
replace the current single Step-Functions-sequenced `bronze -> silver -> MDM
-> gold` chain across all workflows (`load_history`, `bootstrap`,
`daily_incremental`, and the recovery/replay machines). Done when someone can
implement the new architecture — message substrate, event granularity,
consumer boundaries, silver-write concurrency model, gold compute location,
MDM's role, completeness/watermark signaling, and migration sequencing from
the current live pipeline — without further architecture debate.

**Correction (2026-08-11):** the destination originally described gold as a
"dual path" (warehouse Python gold-models vs. Snowflake-native
`EDGARTOOLS_SOURCE` + dbt) needing unification. [Decide the fate of the dual
gold path](issues/05-decide-dual-gold-path-fate.md) found that premise
factually wrong — there is one compute engine (Python), and Snowflake/dbt is
a thin publish/mirror layer over its output, not an independent computation.
The real open question that framing was reaching for is narrower and lives at
[Decide whether gold compute stays in Python/DuckDB or moves into Snowflake
SQL](issues/08-decide-gold-compute-location.md).

## Notes

- Repo: `edgartools-platform`. Design-only map (wayfinder default) — a normal
  implementation session builds from the locked architecture afterward,
  itself likely broken into its own phased-migration plan (see "Not yet
  specified" below).
- Motivation (destination-naming round, 2026-08-10): **independent
  scaling / operational flexibility**. Bronze capture (SEC-rate-limited,
  I/O-bound) and silver/gold builds (CPU/memory-bound) have very different
  resource profiles but currently share task sizing and scheduling inside
  one Step Functions execution.
- Motivation, sharpened (2026-08-11): concrete target is eliminating
  multi-day pipeline runtimes — no `MaxConcurrency=1`-style architectural
  ceilings, for backfill or steady-state. Verified live where that ceiling
  actually comes from today: **not** SEC's rate limit (intra-window
  artifact fetch already runs concurrent, `ThreadPoolExecutor`-parallel,
  independently throttled) — it's `WindowedBootstrap`'s window-level
  `MaxConcurrency=1`, which exists for silver-write safety (see [ticket
  01](issues/01-research-silver-duckdb-concurrent-write-model.md)). This
  surfaced a finer layering worth keeping explicit through the rest of this
  map: **fetch** (SEC-rate-limited, already reasonably parallel) | **parse**
  (bronze bytes -> typed records, CPU-bound, no correctness constraint,
  should scale to full parallelism regardless of storage backend) | **write**
  (the actually-constrained step — DuckDB concurrency fix vs. a different
  storage target entirely, see [ticket
  09](issues/09-decide-silver-write-storage-target.md)). Don't collapse
  "parse" and "write" back into one "silver" bucket when reasoning about
  scalability — they have different fixes.
- Decoupling shape (locked): **both** structural (bronze capture as its own
  deployable unit) and temporal (async/event-driven handoff via messaging) —
  not just a cleaner synchronous split.
- Scope (locked): **both** layer-pairs — the warehouse's own silver
  (`silver.duckdb`) + gold (`edgar_warehouse/gold.py`,
  `serving/gold_models.py`) AND Snowflake's `EDGARTOOLS_SOURCE` + dbt
  `EDGARTOOLS_GOLD`. (Correction, 2026-08-11: these are not two competing
  computations to collapse — see [Decide the fate of the dual gold
  path](issues/05-decide-dual-gold-path-fate.md). Both layers stay in scope
  because gold's *compute location* between them is still an open question,
  now [ticket 08](issues/08-decide-gold-compute-location.md).)
- Cost stance (locked, 2026-08-11, user directive): **on-demand only,
  never always-on — cheapest viable option, not a soft preference.**
  [Ticket 14](issues/14-assess-cost-infrastructure-footprint.md) found a
  warm always-on reducer costs 2-5x more than task-per-batch for the same
  role even though both are individually cheap in absolute terms
  ($21-46/month vs. single-digit dollars); this directive settles that
  gap unconditionally toward on-demand, not case-by-case. Also locks
  Fargate Spot for the parallel-worker queue specifically (SQS redelivery
  already makes workers interrupt-tolerant, so Spot's ~70%-off pricing is
  close to free money there) — not the reducer, where interruption
  mid-merge is a failure mode [ticket 13](issues/13-decide-failure-retry-dead-letter-semantics.md)
  needs to design around deliberately first. Carries forward as a
  constraint on tickets 12 and 13: no shadow/parallel-run infrastructure
  in ticket 12's migration sequencing should be always-on either, and
  ticket 13's retry/DLQ mechanism should default to on-demand primitives
  (CloudWatch alarms + on-demand processing) over any continuously-running
  monitor.
- Rollout stance (locked): **full replacement** is the target end-state, not
  an additive path kept forever alongside the current one — chosen with
  eyes open that this repo has a live production pipeline (a full-universe
  `load_history` backfill just completed 2026-08-10; MDM/gold pipelines run
  daily). Migration sequencing from here to there is real fog (see below),
  not assumed to be a big-bang cutover.
- Current architecture baseline (read from `docs/data-architecture.md`
  2026-08-10, do not re-derive): bronze capture and silver parse happen in
  the *same* warehouse process/command today (e.g. `bootstrap-next` writes
  bronze and parses to silver in one execution) — genuinely coupled, not
  just co-scheduled. `gold-refresh` reads the *complete* silver DuckDB (not
  bronze directly) and only runs after the full MDM chain
  (`mdm run -> backfill-relationships -> export -> sync-graph -> verify-graph`)
  completes, all inside one long `load_history`/`bootstrap`/`daily_incremental`
  execution. One hop is *already* decoupled/messaging-driven: gold's Snowflake
  ingestion leg (S3 export Parquet -> storage integration -> S3-event ->
  SNS -> `SNOWFLAKE_RUN_MANIFEST_TASK` -> `EDGARTOOLS_SOURCE` -> dbt ->
  `EDGARTOOLS_GOLD`). Everything upstream of that is still one synchronous
  chain. `silver_mdm_gold`/`bronze_seed_silver_gold` already exist as
  operator-triggered (not automatic) bronze-replay tools that avoid new SEC
  calls — a partial precedent for "inject already-loaded bronze downstream
  independently," just not event-driven.
- Existing vocabulary to respect, not redefine (`CONTEXT.md`): **Runtime
  System of Engagement** (silver), **SecGateway**, **Silver-Once
  Idempotency**, **Bronze Persist**, **Daily-Artifact Run Manifest** /
  **Outcome Ledger**, **Decision Watermark** / **Release Data Watermark** /
  **Relationship Generation Snapshot** — this last group is real prior art
  for whatever "silver/gold completeness" signal this map ends up needing
  (ticket: [Decide the completeness/watermark signal for async silver and
  gold](issues/07-decide-completeness-watermark-signal.md)).
- Prior art / do not re-litigate: the
  [state-machine-consolidation](../state-machine-consolidation/map.md) and
  [stage0-stage1-consolidation](../stage0-stage1-consolidation/map.md) maps
  (both just closed, 2026-08-10) already established the MDM-tail/MDM-Utility-
  Machine boundaries and `load_history`'s phase sequencing — build on top of
  those, don't redo them.
- Skills every session on this map should consult: `/gof-refactor-reviewer`
  (given the scale, worth checking real evidence before locking any specific
  mechanism), `/grilling` + `/domain-modeling` for grilling tickets,
  `/research` subagent for fact-finding tickets.

## Decisions so far

- [Decide the fate of the dual gold path](issues/05-decide-dual-gold-path-fate.md) — the "dual path" premise was factually wrong: gold has exactly one compute engine (Python's `iter_gold_tables()`); Snowflake/dbt is a thin publish/mirror layer over its output, not an independent computation. Real question split off to [ticket 08](issues/08-decide-gold-compute-location.md).
- [Investigate silver DuckDB's current concurrent-write model](issues/01-research-silver-duckdb-concurrent-write-model.md) — sharding is not write-safe today (read-only reader, one narrow unprotected write path, safe only by scheduling convention); the ticket-20 race was logical-consistency, not corruption, and the system fails closed by design; two proven-safe concurrent-write patterns (ETag-guarded merge/retry, isolated-producer+reducer) already run in prod against DuckDB. Evidence favors fixing DuckDB concurrency over moving off it, with an explicitly unresolved caveat on cost-at-scale vs. Snowflake-native `MERGE`. Feeds [ticket 09](issues/09-decide-silver-write-storage-target.md), now unblocked.
- [Decide silver's write/storage target](issues/09-decide-silver-write-storage-target.md) — keep DuckDB, fix concurrency (extract the ETag-guard as a shared helper; generalize the existing isolated-producer+reducer pattern to fire per-event). Decided on engineering-cost grounds; cost-at-scale vs. Snowflake `MERGE` at real event frequency is an accepted open risk, revisit if [ticket 02](issues/02-research-messaging-substrate-options.md) surfaces a reason to. Pulls [ticket 08](issues/08-decide-gold-compute-location.md) toward its option (a) — silver staying on DuckDB removes gold option (b)'s main enabler — but doesn't resolve ticket 08.
- [Map which gold tables depend on MDM output](issues/03-research-mdm-gold-dependency-mapping.md) — MDM dependency is far narrower than assumed: 0 of 28 Python gold builders touch MDM at all; only 1 real gold surface (`EDGARTOOLS_GOLD.COMPANY`, a `LEFT JOIN` enrichment) depends on MDM, and only on entity-resolution output, never any relationship type. Supports MDM becoming a narrow, optional gold consumer — except the Decision Contract's Subject Universe, which has a hard, non-optional filter on MDM's `tracking_status`. Separately surfaced that graph sync (`NEO4J_GRAPH_MIGRATION`) is its own decoupling boundary, independent of gold: 3 live consumers (main dashboard's Relationships tab, its freshness strip, Decision Contract's Agent View) all bypass gold and read the graph schema directly. Feeds [ticket 06](issues/06-decide-mdm-role-in-new-architecture.md), now unblocked.
- [Decide MDM's role in the decoupled architecture](issues/06-decide-mdm-role-in-new-architecture.md) — MDM becomes an independent async consumer, system of record for all 5 master-data domains it resolves (not just company), and gold never blocks on it — except the Decision Contract's Agent View, which gets its own explicit "MDM-resolved" readiness gate rather than silently omitting unresolved companies. Must also seamlessly support company *discovery* (seed-universe, sourced from SEC's index, not a parsed filing) as a first-class event, not a bolted-on synchronous special case — open question folded into [ticket 04](issues/04-decide-event-granularity.md). Relationship derivation/graph sync graduated into its own ticket, [ticket 10](issues/10-decide-graph-sync-role-in-new-architecture.md).
- [Decide graph sync's role in the decoupled architecture](issues/10-decide-graph-sync-role-in-new-architecture.md) — symmetric split with ticket 06: MDM is system of record for entities, graph is system of record for relationships (MDM's own `mdm_relationship_instance` is working data, not authoritative). Relationship derivation and graph sync both become independent async consumers, on their own cadence. `GRAPH_ACTIVE_POINTER` already provides the needed watermark mechanism — just needs to advance per-event — which resolves graph's slice of [ticket 07](issues/07-decide-completeness-watermark-signal.md) directly rather than just informing it. Surfaced a recurring implementation pattern (generalize an existing one-shot reducer to fire per-event) shared with tickets 06 and 09.
- [Finalize the company-discovery event flow](issues/11-finalize-company-discovery-event-flow.md) — traced today's actual flow and found duplicated capability with an inverted ownership arrow: warehouse fetches/dedupes SEC's index and MDM re-imports secondhand from silver. Resolved: MDM owns the fetch, dedup, and all cleaning directly (promoting its currently-discouraged `--source edgartools` path to primary, retiring `--source silver`); warehouse's role becomes purely reactive bookkeeping to an MDM-published event. Discovery does not need to directly trigger bronze capture — a newly-seeded CIK becomes indistinguishable from any other tracked CIK immediately. Trigger cadence and messaging substrate remain open. Revises the shape of two already-closed decisions in other maps (`state-machine-consolidation` ticket 04, `seed-universe-narrow-hydrate` ticket 05) — noted, not reopened.
- [Decide whether gold compute stays in Python/DuckDB or moves into Snowflake SQL](issues/08-decide-gold-compute-location.md) — (a), sharpened: Python computes gold from silver; Snowflake only computes where inputs genuinely only co-exist in Snowflake (the 3 existing real-transformation dbt models, kept as a bounded exception, not a contradiction). Only the delivery mechanism becomes message-driven; compute engine, table count, and per-table split are unchanged. Every prior ticket's evidence (09's DuckDB-stays decision, 02's Snowpipe-Streaming-not-worth-it finding, 04's Python/ECS-centric async design) pointed the same direction. Closes the last open grilling ticket from the original scope — migration sequencing, failure semantics, and cost footprint graduated into [tickets 12](issues/12-sequence-the-migration.md), [13](issues/13-decide-failure-retry-dead-letter-semantics.md), [14](issues/14-assess-cost-infrastructure-footprint.md).
- [Decide the completeness/watermark signal for async silver and gold](issues/07-decide-completeness-watermark-signal.md) — reuses `CONTEXT.md`'s existing Decision Watermark composite as-is (silver completeness, graph generation id, gold/feature as-of, business date), no new shape invented. MDM's readiness doesn't need a fifth component — the Decision Subject Universe's existing membership filter (`tracking_status='active'`) already is ticket 06's gate. Gold's own `edgartools_gold_status`/`SERVING_REFRESH_STATUS` is a fourth instance of the same "generalize a per-run signal to per-event" pattern already applied to silver (09), MDM (06), and graph (10). Only [ticket 08](issues/08-decide-gold-compute-location.md) remains open.
- [Decide event granularity for bronze-write triggers](issues/04-decide-event-granularity.md) — per-accession, not per-object or per-window: bronze capture emits one event per accession once its full configured document set is captured (reusing the existing `_configured_parser_accessions` completeness check), not per individual object write. The silver-write reducer batches on a fixed N-or-timer trigger (EventBridge Pipes native), no meaningful-boundary logic. One accession-complete event fans out to two SQS queues per ticket 02's design — near-1-batch-size for parallel parse workers, larger-batch/timer for the reducer. Unblocks [ticket 07](issues/07-decide-completeness-watermark-signal.md).
- [Research AWS messaging substrate options](issues/02-research-messaging-substrate-options.md) — S3→SNS→multiple SQS subscriptions is the natural extension of this repo's live precedent (additive to the existing Terraform-managed topic); EventBridge is a real alternative already operated in this account (different job today) with a genuine content-based-filtering edge; Kinesis ruled out (no S3 native destination, ~$28.80/month fixed floor, replay capability this map doesn't need). The fan-out/reducer duality (tickets 06/09/10) maps onto **two** independently-configured SQS queues off one SNS topic, not one shared queue. Cost is negligible across S3/SNS/SQS/EventBridge at this platform's real volume (~625K objects, under $2 total) — does not push ticket 04 toward coarser granularity. Snowpipe Streaming not worth adopting for the existing gold-export path (cost parity since Dec 2025, would replace not extend the write path) — carried to ticket 08. No standing repo constraint rules out any candidate. Directly unblocks [ticket 04](issues/04-decide-event-granularity.md).
- [Decide failure/retry/dead-letter semantics for the new async consumers](issues/13-decide-failure-retry-dead-letter-semantics.md) — retry policy differs per queue (parallel-worker: moderate maxReceiveCount; reducer: smaller, since `PromotionConflictError` retries are already handled in application logic). DLQ alerting reuses the existing `pipeline_notifications` SNS topic. Poison-message handling reuses this repo's existing fail-closed philosophy, no new classifier. Found and **fixed** a real gap (not just noted): `activate_graph_generation` validated generation status but not recency — an out-of-order SQS delivery could have silently regressed the active graph. Implemented a monotonicity guard on branch `claude/graph-generation-activation-monotonicity` (reviewed via `/gof-refactor-reviewer` first — a guard-clause fix, not a pattern), 4 new tests, full file suite green.
- [Sequence the migration from the current live pipeline to the decoupled architecture](issues/12-sequence-the-migration.md) — Phase 0: validate the silver async reducer in isolation (synthetic/replayed events, no live data) before any live cutover, since it's the highest-risk, most novel piece on this map. Then a live phased cutover in dependency order: bronze → silver → {MDM, graph independently} → gold's delivery leg. Rejects both big-bang and full parallel-run (shadowing against live data reintroduces the dual-writer hazard tickets 01/09 fixed). In-flight executions coexist, don't drain (confirmed empirically this session). Rollback is per-component, not whole-system. No phase introduces always-on compute, per the locked cost stance.
- [Assess cost/infrastructure-footprint implications of the new async architecture](issues/14-assess-cost-infrastructure-footprint.md) — compute cost (as opposed to ticket 02's already-priced messaging cost) is cheap at any sane batch size: the one-time 625K-event backfill costs roughly $3-$316 (batch 10-100, all three task sizes, floor-only to cold-image-pull-inclusive), and today's on-demand `WindowedBootstrap` baseline itself only costs $1.76 — Fargate bills reserved-capacity × wall-clock-time, so there isn't much idle-capacity waste to recover, and the new architecture's real payoff is removing the `MaxConcurrency=1` throughput ceiling, not compute-dollar savings. Batch size 1 (true task-per-message) is genuinely expensive ($309-$3,164 for the backfill) and independently ruled out by Fargate's 500-tasks/minute provisioning ceiling regardless of cost — reinforcing ticket 04's already-locked batched design on a third axis. ECS Service Auto Scaling can genuinely scale to zero, undercutting the premise that a long-running reducer must pay an idle-capacity floor — but scaling to zero reintroduces the same cold-start latency task-per-message has; a warm (`minCapacity=1`) reducer costs $21-46/month, ~2-5x more than task-per-batch for the same role. Recommends task-per-batch (not literally per-message, not a long-running service) for both queues. No new fixed AWS cost beyond the reducer floor if a long-running service were chosen instead, but a long-running reducer would be a genuinely new Terraform resource-type surface for this repo (zero `aws_ecs_service`/`aws_appautoscaling_*`/`aws_cloudwatch_metric_alarm` exist today). Finds cost should not gate ticket 12's sequencing decision, and that ticket 13's retry/DLQ semantics need to be batch-level, not per-message, given the batch sizes this ticket recommends.

## Pre-implementation review (2026-08-11)

`/gof-refactor-reviewer` pass over the "generalize a per-run reducer to
per-event" pattern shared across tickets 06/09/10/07, before handoff:
**this is a shared design principle, not shared code — do not extract one
implementation across it.** Read all three Python/Snowflake mechanisms
directly (`warehouse_orchestrator.py:980-1063` silver ETag-guarded S3
stage+promote; `mdm/export.py:207-260` MDM's Snowflake `MERGE` via temp
table; `mdm/cli.py:1626`/`snowflake_graph.py` graph's pointer-flip
function) — each is native to its own storage substrate with no shared
interface or runtime; ticket 07's `edgartools_gold_status` piece is
dbt/SQL, a fourth substrate again. An implementer should treat "generalize
to per-event" as four separate, substrate-native changes, each checked
against the same design principle for consistency — not one abstraction
four call sites share. The one genuine code-level duplication-with-drift
finding (`_publish_shard_if_remote` missing the ETag guard
`_publish_silver_database_if_remote` already has) is real, already scoped
in [ticket 09](issues/09-decide-silver-write-storage-target.md), and needs
no further design work — Extract Function, not a pattern.

## Not yet specified

(none — all three items graduated into tickets 12/13/14 once the target
architecture locked with ticket 08's resolution, 2026-08-11)

## Out of scope

(none yet — scope hasn't narrowed enough to rule anything out)
