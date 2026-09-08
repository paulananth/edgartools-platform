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
3. [Batch skip-if-unchanged source-ref lookup](issues/03-batch-skip-if-unchanged-source-ref-lookup.md) — resolved: `BaseResolver._skip_if_unchanged`'s per-row `mdm_source_ref` SELECT (49,425 of ~57K SQL calls in one live run's first 14 minutes) is now one bulk prefetch per batch (`ResolverContext.prefetched_source_refs`, keyed `(source_system, source_id)`), built before any worker thread starts and threaded through every resolver's `ResolverContext`. Round-trip *count* proven flat via regression tests; wall-clock impact measured live on 2026-09-07: company resolution dropped from 37.7min (73,691 rows) to 77s (50,735 rows), a ~23x improvement, decisively closing this map's own "real measurements" ask.
4. [_run_grouped_concurrent single end-of-group commit](issues/04-run-grouped-concurrent-single-end-of-group-commit.md) — resolved: `_process_group` now commits every `commit_interval` (default 1000) rows within a group's loop, not only once at the end. Live-verified 2026-09-08 against fresh prod data (`mdm-mastering-groupcommit-verify-1788827772`): the exact entity flagged in this ticket's original investigation showed two independent periodic commits ~10 minutes apart (513 → 1017 accumulated rows), each landing as a burst of durable, externally-visible progress mid-group — the intended behavior, replacing the original incident's single all-or-nothing commit after 20+ minutes of total invisibility.
6. [Relationship-derivation batch-level commit](issues/06-relationship-derivation-batch-level-commit.md) — resolved: `_derive_institutional_holds`/`_derive_manages_fund` now commit at their existing CIK/CRD-range batch boundary, not just once at the end of the whole relationship type. Found live: `INSTITUTIONAL_HOLDS` (6.8M-row `sec_thirteenf_holding`) sat on one uncommitted transaction for 3h24min+ during a real `daily_incremental` run — the same shape as Ticket 04, in a sibling code path. Full audit confirmed zero commits exist in any of the 11 `_derive_*` methods; scoped narrowly to the two with an existing batch structure (7 others proven sub-second live, `_derive_holds`/`_derive_company_holds` need a separate unbounded-fetch fix first). Not yet deployed as of this entry.

## Not yet specified

- Ticket 03's batching win was verified structurally (SQL round-trip count
  stays flat as row count grows) but not with a live wall-clock before/after
  comparison at 16-way concurrency in prod, which this map's own standing
  preference asks for. Capture that on the next prod deploy that includes
  the fix -- compare against the 2026-09-07 baseline already on record
  (company resolution: 37.7 min for 73,691 rows pre-fix).
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
- [mdm_entity_attribute_stage unbounded candidate accumulation](issues/05-mdm-entity-attribute-stage-unbounded-candidate-accumulation.md)
  -- open, not yet claimed: found live while verifying Ticket 04. A handful
  of heavily-refiled securities (up to 5,048 accumulated stage rows for one
  entity/field, all-history) make `run_survivorship_for_entity`'s SELECT pay
  a long-tail cost (611-619ms max vs. 0.15-0.51ms mean, confirmed via
  `pg_stat_statements`) on top of this map's own already-documented flat
  ~68-100ms cross-region round-trip cost. Separate from both Ticket 04
  (durability/visibility, not speed) and concurrency (no contention evidence
  found at any level -- Postgres CPU idle, ECS CPU ~20-35%, zero blocked
  queries).

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
