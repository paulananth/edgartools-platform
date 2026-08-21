# MDM run step parallelism

Labels: wayfinder:map

## Destination

A locked decision on whether/how to run `MDMPipeline`'s five
entity-resolution steps (company, adviser, security, person, fund)
concurrently with each other inside `mdm run`, instead of strictly
sequentially in `run_all()` (`edgar_warehouse/mdm/pipeline.py` ~line 1650:
`run_companies -> run_advisers -> run_securities -> run_persons ->
run_funds -> derive_relationships`). Reaching the end of this map means
someone can start implementing (or can confidently decide not to) without
hitting an undecided design question: whether the wall-clock win is real
once real per-step timing is measured, what shape the parallelism takes
(in-process thread pool vs. multi-ECS-task/Step-Functions Parallel state),
and whether the existing MDM Postgres connection-pool budget can safely
absorb several steps' internal worker pools running at once.

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py` (`MDMPipeline.run_all`),
  `infra/scripts/deploy-aws-application.sh` (`edgartools-prod-mdm-run`'s
  Step Functions definition, currently always `mdm run --entity-type all`
  as one ECS task).
- Trigger: observed live in this session — the CLI already supports running
  each entity type independently (`--entity-type {company,adviser,security,
  person,fund,all}`, `edgar_warehouse/mdm/cli.py`), confirmed by actually
  launching `mdm run --entity-type person` and `mdm run --entity-type
  security` as two separate standalone ECS tasks to verify an unrelated
  feature (mdm-ahead-of-silver's backfill sweep). The user pointed out
  these clearly don't have to run sequentially.
- **Goal (settled 2026-08-19): wall-clock speed of `mdm run --entity-type
  all`**, not compute-cost reduction — matters because other pipelines
  (the mdm-ahead-of-silver backfill sweep, gold refresh, graph sync) wait
  on MDM resolution finishing before they can proceed.
- **Security's soft dependency on company (settled 2026-08-19): acceptable
  for security to run before company finishes.** `run_securities()` can
  create a security row with a NULL `issuer_entity_id` if its issuer
  company hasn't resolved into `mdm_company` yet;
  `backfill_security_issuers()` (`pipeline.py` ~line 1601) already exists
  specifically to repair that afterward. Don't force company-before-security
  ordering under parallelism just to avoid exercising this already-built
  repair path.
- **Prior art — do not re-derive**: the
  [mdm-run-throughput](../mdm-run-throughput/map.md) map already
  parallelized *within* each of run_companies/run_securities/run_persons
  (bounded `ThreadPoolExecutor`, default 16 workers/domain via
  `MDM_RESOLVE_CONCURRENCY`, grouped-by-key to keep match-candidate lookups
  safe under concurrency). Its root-cause finding matters directly here:
  every MDM Postgres SQL round trip costs a flat ~68ms because the Postgres
  endpoint is in `us-west-2` while ECS warehouse tasks run in `us-east-1` —
  real cross-region latency, not a pooling misconfiguration. Concurrency
  hides this cost; parallelizing across steps as this map considers would
  need to reckon with the *same* fixed per-call floor, multiplied by
  however many steps' worker pools are active simultaneously.
  `run_advisers`/`run_funds` are explicitly **out of scope** for that map
  because they're already bulk/batched (`edgar_warehouse/mdm/adv_bulk.py`),
  not the naive per-row loop shape — worth remembering here too, since they
  may already be fast enough that overlapping them with the other three
  buys little.
- The separate [pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)
  map explicitly ruled MDM/graph-sync stages out of its own scope ("run on
  a separate Postgres+graph path with their own cost model... a future map
  can cover them if warranted") — this map is that future map, but for the
  cross-step axis specifically, not the within-step axis mdm-run-throughput
  already covered.
- **Live data point gathered while charting this map (2026-08-19, not a
  formal measurement — see ticket 01)**: a standalone `mdm run
  --entity-type person` task finished in ~1m55s (16:46:05–16:48:00 ET). A
  concurrently-started `mdm run --entity-type security` task was **still
  running after 25+ minutes** (started 16:46:16 ET, still actively issuing
  real `mdm_sql_*` calls at 17:11:41 ET, not stuck/hung) against the same
  silver dataset. This asymmetry is worth taking seriously before assuming
  an even 5-way split — if security alone dominates wall-clock time, the
  achievable win from overlapping the *other* four steps with it may be
  much smaller than naively splitting 5 sequential steps into 5 parallel
  ones would suggest. Ticket 01 should capture the real, complete number
  once that task (or a fresh comparable one) finishes.
- Mode: decision-spec only (wayfinder default, not overridden) — this map
  produces a decision, not shipped code.

## Decisions so far

- [Goal is wall-clock speed, not cost](.) — settled directly during
  chartering (2026-08-19); not a standalone ticket, recorded here since it
  shapes every downstream ticket's framing.
- [Security-before-company ordering is not required under parallelism](.) —
  settled directly during chartering (2026-08-19); `backfill_security_issuers()`'s
  existing repair path is sufficient. Also recorded here rather than as a
  standalone ticket.
- [Measure Per-Step Timing and Connection-Pool Ceiling](issues/01-measure-per-step-timing-and-connection-pool-ceiling.md)
  — real measured durations: `adviser` 31s, `fund` 53s, `person` ~1m55s,
  `security` 1h50m31s (20,683 rows), `company` 2h14m7s (67,870 rows). The
  two bulk/batched steps are negligible; `company` and `security` dominate
  and are the only steps worth parallelizing against each other. Connection-
  pool math: in-process 3-way overlap of company+security+person would
  over-subscribe the current 30-connection pool ~1.7x (degrades to queueing,
  not failure); multi-task shape isolates pools per step but needs the same
  total headroom. Postgres server-side `max_connections` remains unknown —
  carried to ticket 02 as a pre-decision fact-check. Also surfaced (not
  chased): `company`'s run only added ~63 net-new rows across 67,870
  processed, suggesting its "skip-if-unchanged fast path" (commit
  `7ffda2d7`) may not be effectively skipping real work.
- [Decide the Parallelism Shape (or Decide Not To)](issues/02-decide-parallelism-shape.md)
  — **build it**: in-process concurrency, all 5 entity-resolution steps
  launched as concurrent top-level futures inside the existing single
  `MdmRun` ECS task (each step keeps its own existing worker pool
  unchanged), fail-fast on any step's exception,
  `derive_relationships()`'s trigger stays unchanged (still waits for all
  5), `MDM_DB_POOL_SIZE=40`/`MDM_DB_MAX_OVERFLOW=20`. Rejected the
  multi-ECS-task/Step-Functions `Parallel` shape once a new fact
  (Postgres server `max_connections=500`, only 13 active — confirmed live)
  showed the connection-pool ceiling that made per-step isolation look
  necessary is actually a cheap-to-raise client-side setting, not a real
  constraint. This resolves the map's own destination question in full —
  see "Frontier" below. **Built 2026-08-20, commit `517f7eff`** — see the
  ticket for a fail-fast bug a code review caught and fixed before it
  shipped (a naive executor shutdown would have blocked the "propagates
  immediately" guarantee), and for the deferred runtime-only verification
  (CloudWatch overlap-count) that genuine 5-way concurrency is live.

## Frontier (open tickets)

None. Ticket 02 resolved the map's full destination question (whether/how
to run the five entity-resolution steps concurrently). This map's
destination is reached — someone can start implementing the decision above
without hitting an undecided design question.

## Not yet specified

<!-- fog beyond the frontier ticket below -->

None — both items previously here graduated into explicit deferrals inside
ticket 02's own resolution, not into further fog on this map (see "Out of
scope" below for why they don't belong to this map's own destination).

## Out of scope

- **Whether `derive_relationships()` could start early for relationship
  types that only depend on a subset of entity types.** Ticket 02
  considered this directly and deliberately kept `derive_relationships()`'s
  trigger unchanged (still waits for all 5 entity steps) — this map's
  destination was "whether/how the five entity-resolution steps run
  concurrently with each other," not the finer-grained question of
  relationship-type-level startup dependencies. Genuinely a separate,
  bigger design question (which of the 11 relationship types depend on
  which entity types, whether partial availability is safe) — deserves its
  own future ticket/map, not a fold-in here.
- **Whether `company`'s skip-if-unchanged fast path (commit `7ffda2d7`) is
  actually skipping real work.** Ticket 01 found `company` processed 67,870
  rows in 8,046s while only ~63 were net-new — a real, concrete finding,
  but a `company`-resolution correctness/performance question, not a
  cross-step-parallelism one. Never claimed as in-scope for this map's
  destination; noted here (not lost) for whoever charts that separate
  effort.
