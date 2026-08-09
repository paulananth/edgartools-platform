# MDM run throughput

## Destination

A locked decision on whether/how to safely speed up `MDMPipeline`'s
remaining single-threaded, per-row resolver loops (`run_securities`,
`run_persons`) the same way `run_companies` was fixed (PR #376) --
covering the correctness constraint each domain's match-candidate lookup
imposes on concurrent execution. Explicitly out of scope for the
[pipeline-throughput-architecture](../pipeline-throughput-architecture/map.md)
map ("MDM / graph-sync stages ... run on a separate Postgres+graph path
with their own cost model" -- that map's own Out of scope section flagged
"a future map can cover them if warranted"; this is that map).

## Notes

- Domain: `edgar_warehouse/mdm/pipeline.py` (MDMPipeline.run_securities,
  run_persons), `edgar_warehouse/mdm/resolvers/security.py`,
  `edgar_warehouse/mdm/resolvers/person.py`.
- Root cause of the underlying slowness (shared by all of MDM's per-row
  resolver loops, not just company): every MDM Postgres SQL round trip
  measures a flat ~68ms regardless of work done -- the MDM Postgres
  endpoint resolves to `us-west-2`, ECS warehouse tasks run in `us-east-1`.
  Real, structural cross-region latency, not a pooling misconfiguration.
  Concurrency hides this; it doesn't reduce it.
- Standing preference from the parent session: real measurements, not
  estimates.

## Decisions so far

1. [Fix run_companies concurrency](https://github.com/paulananth/edgartools-platform/pull/376) — resolved (implemented directly, not decision-spec-only, given live production time pressure): company resolution moved to a bounded `ThreadPoolExecutor` (default 8 workers, one session per worker). Safe because `CompanyResolver._existing_candidates` scopes its match lookup to the row's own CIK -- a true 1:1 natural key, no cross-row shared match state, and CIK-exact rematching makes retries idempotent. Real measured baseline: 62,190 companies at ~2.16s/row (~37h projected) before the fix.
2. Fix run_securities/run_persons concurrency — resolved (implemented directly, live production time pressure, same as decision 1): picked the "pre-group rows and parallelize across groups, serialize within a group" option over a DB-level unique constraint + upsert. `MDMPipeline._run_grouped_concurrent` (new shared helper in `pipeline.py`) partitions rows by a caller-supplied key, runs each group's rows sequentially on one worker/session, and different groups run concurrently across a bounded thread pool -- the group-per-row-set generalization of run_companies' per-row pattern. `run_securities` groups by `canonical_title` alone, not `(issuer, title)` as originally guessed above -- `SecurityResolver.resolve_one`'s "upgrade a NULL-issuer security" path lets two *different* issuers sharing one title interact, so the real concurrency boundary is the title alone (issuer doesn't further partition it). `run_persons` groups CIK-scoped rows by `owner_cik` (safe, same shape as company); rows with `owner_cik IS NULL` (the unscoped fuzzy-match fallback) stay single-threaded, run strictly after the CIK-scoped batch commits. Default worker count for all three domains (company/security/person) raised to 16 (env: `MDM_RESOLVE_CONCURRENCY`, with per-domain overrides); `database.py`'s connection pool budget (`MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW`, both default 15) raised in step so 16 workers + the pipeline's own primary session doesn't exceed the old SQLAlchemy QueuePool default (5+10=15). Tests: `tests/mdm/test_run_securities_persons_concurrency.py` (grouping-boundary correctness under real multi-threaded execution, the null-issuer-upgrade race, the unscoped fuzzy-merge staying correct, default-worker-count assertions), `tests/mdm/test_database_pool_config.py`.

## Not yet specified

- Real per-domain row counts and sequential-runtime baselines for
  `run_securities`/`run_persons` were estimated from raw table counts during
  the parent investigation (~15,000 and 7,911 respectively) -- not yet
  measured the same rigorous way ticket-style (real `mdm_progress` log
  deltas) as company's 62,190/2.16s baseline was. Decision 2's fix should
  make this easy to re-measure live once deployed and re-run.
- Whether the currently-running prod `bronze_seed_silver_gold` execution
  (started before decision 2's image was built) should be restarted to pick
  up the fix, vs. letting it finish on the old single-threaded code and
  applying the fix starting with the next execution -- an operational
  deploy-timing call, not a design question this map tracks.

## Out of scope

- `run_advisers`/`run_funds` -- already implemented as a bulk/batched
  operation (`edgar_warehouse/mdm/adv_bulk.py`, `_chunks`/`_WRITE_BATCH_SIZE`),
  not the naive per-row `resolve_one` loop shape this map is about. Not
  subject to the same bottleneck despite adviser's large raw row count
  (234,396 ADV filings) and fund's very large one (1,579,876 private funds).
- Reducing the underlying ~68ms cross-region round-trip latency itself
  (e.g. relocating the Snowflake Postgres instance's region, or relocating
  ECS compute to us-west-2) -- a much larger infrastructure decision than
  this map's scope, and concurrency already provides most of the practical
  win without it.
