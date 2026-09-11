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
6. [Relationship-derivation batch-level commit](issues/06-relationship-derivation-batch-level-commit.md) — resolved: `_derive_institutional_holds`/`_derive_manages_fund` now commit at their existing CIK/CRD-range batch boundary, not just once at the end of the whole relationship type. Found live: `INSTITUTIONAL_HOLDS` (6.8M-row `sec_thirteenf_holding`) sat on one uncommitted transaction for 3h24min+ during a real `daily_incremental` run — the same shape as Ticket 04, in a sibling code path. Full audit confirmed zero commits exist in any of the 11 `_derive_*` methods; scoped narrowly to the two with an existing batch structure (7 others proven sub-second live, `_derive_holds`/`_derive_company_holds` need a separate unbounded-fetch fix first). Deployed and live-verified 2026-09-08: a full scoped run (9,900 rows, ~35.5 min) landed in six distinct commit bursts spread across the run, not one commit at the end.
7. [INSTITUTIONAL_HOLDS CUSIP lookup memoization](issues/07-institutional-holds-cusip-lookup-memoization.md) — resolved: `_ensure_security_by_cusip` now memoizes cusip → entity_id (shared across CIK-range batches, same shape as the sibling `adviser_id_by_cik` cache), while still preserving the opportunistic `security_class` backfill correctness. Real measurement: `sec_thirteenf_holding` has 6,799,919 rows across only 41,225 distinct CUSIPs (~165x repetition) — this was the dominant unmemoized per-row cost in the whole path. Also confirmed live: 13F ingestion is already correctly bounded to a 2-year lookback by default (`DEFAULT_FUNDAMENTALS_LOOKBACK_YEARS`), so the 6.8M-row figure isn't loaded wider than intended. **Deployed and live-verified 2026-09-08** (PR #572): a scoped prod run showed 8,056 relationships created against only 1,626 CUSIP SELECTs (~20% round-trip rate), confirming the cache. This commit is an ancestor of `main` and every image deployed since (including today's) already carries it.
5. [mdm_entity_attribute_stage unbounded candidate accumulation](issues/05-mdm-entity-attribute-stage-unbounded-candidate-accumulation.md) — resolved: confirmed live that every row in a bloated group shares one value (5,048 rows, 1 distinct value for the worst entity) -- genuinely distinct real transactions, not a bug `_skip_if_unchanged` should have caught. Built both a write-time guard (`stage_candidate()`'s new `representative_cache` param, wired only into `_run_grouped_concurrent`'s per-group `ResolverContext`) and a one-time backfill CLI (`mdm collapse-attribute-stage-history`, new `attribute_stage_backfill.py`; supports `--dry-run` and `--limit` for a bounded correctness check, real run by default). A pre-code `/gof-refactor-reviewer` pass caught that a naive per-call lookup would double round trips on the dominant path (`_skip_if_unchanged` already filters reprocessed rows, so almost every call carries a brand-new `source_id`); fixed with a lazy per-group cache instead of an eager whole-batch prefetch. The mandatory post-diff 3-axis `/code-review` then caught two further real bugs the design review missed: the retention rule wrongly assumed all 4 survivorship rule types share one sort key (only `most_recent` uses `effective_date`; the other 3 sort purely on `(priority, loaded_at)` — a naive Pareto sort could silently discard the group's true recency champion), and a stale-cache-entry bug where restaging the same `source_id` with a changed value could leave a later new confirmation of the *old* value wrongly merged into the wrong row. Both fixed and covered by new regression tests reproducing each exactly. 29 new tests, full repo suite green (3250 passed, only the 8 pre-existing unrelated Postgres-integration failures). **Deployed and backfilled against real prod 2026-09-11** — the backfill CLI's first live run exposed a second round-trip-batching bug (fixed in a same-day follow-up, PR #588, see the ticket's own entry for the full story); final live numbers: `mdm_entity_attribute_stage` went from 2,577,622 to 1,732,055 rows (845,567 deleted, exact match to the dry-run's independent prediction), real-run throughput improved ~31x (2.8 → 87 entities/sec) after the batching fix.
8. [Was Ticket 03's verification actually at 16-way concurrency?](issues/08-was-ticket03-verification-actually-at-16-way-concurrency.md) — resolved: confirmed via `git log` that Ticket 02's 16-worker concurrency default (PR #381, merged 2026-08-09) was live a full month before the 2026-09-07 verification run that captured Decision 3's 77s/50,735-row company measurement — that number already reflects both fixes together, so the map's former fog note asking for exactly this comparison was already answered elsewhere on the map and just never cleared. No new live prod run needed.

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
