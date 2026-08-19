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

## Not yet specified

<!-- fog beyond the frontier ticket below -->

- Whether `derive_relationships()`'s own placement (strictly after all 5
  resolve steps finish) has any room to start early for relationship types
  that only depend on a subset of entity types — not yet looked at, and may
  turn out to be its own can of worms; deliberately not ticketed until
  ticket 02 (parallelism shape) resolves, since it only matters if this map
  concludes some form of cross-step overlap is worth building at all.
- Whether `company`'s skip-if-unchanged fast path (commit `7ffda2d7`) is
  actually skipping real work — ticket 01 found it processed 67,870 rows in
  8,046s (~119ms/row) while only ~63 were net-new. Not sharp enough to
  ticket yet (haven't confirmed whether the fast path activated at all vs.
  activated but still paid a comparable round-trip cost either way) and may
  belong to a different map entirely (it's a `company`-resolution
  correctness/perf question, not really a cross-step-parallelism one) —
  noted here so it isn't lost, not claimed as in-scope for this map's
  destination.

## Out of scope

<!-- none yet -->
