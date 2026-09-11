Type: task
Status: resolved

## Question

`mdm_entity_attribute_stage` has no pruning anywhere in this codebase (already
flagged in `SecurityResolver.resolve_one`'s own 2026-08-21 comment,
`edgar_warehouse/mdm/resolvers/security.py:71-88`). A handful of heavily-refiled
securities have accumulated thousands of duplicate candidate rows across every
past `mdm mastering` run, and `run_survivorship_for_entity`'s SELECT re-scans
that entire, ever-growing candidate set every single time the entity is
touched (even by a single new row). Should this be pruned/bounded, and how?

## Context

Spawned while directly measuring live production data during
[Ticket 04](04-run-grouped-concurrent-single-end-of-group-commit.md)'s
verification run (`mdm-mastering-groupcommit-verify-1788827772`,
2026-09-08), after the user asked whether Postgres CPU or concurrency
explained the run's slow, bursty write pattern.

Live evidence gathered directly (not estimated):

- **Postgres CPU: idle.** Zero active queries at every point checked during
  the run; all ~18 worker sessions sat `idle` (last statement `COMMIT`).
  `pg_locks` showed zero blocked queries throughout.
- **ECS task CPU: ~20-35% of the allocated 1 vCPU** (`edgartools-prod-mdm-medium`,
  1024 CPU units), one brief startup spike to ~99%, otherwise well under
  capacity the whole run.
- **`pg_stat_statements` (extension 1.10, live in prod)** shows the exact
  `SELECT mdm_entity_attribute_stage...` query `run_survivorship_for_entity`
  issues has a **mean execution time of 0.15-0.51ms** across millions of
  calls, but a **max execution time of 611-619ms** — a long tail two to
  three orders of magnitude past the mean, on the identical query shape.
- **Confirmed the long tail's source directly:** total (all-history, not
  just this run) accumulated stage-row counts per entity/field:
  - `91c364bb-0ee3-4e06-9ae9-648c4747b054`: 5,048
  - `a31e1bdf-523e-4911-bc5b-413e8103376c`: 2,753 (the exact entity from
    Ticket 04's own investigation)
  - `9ce0c694-dc23-4fed-9aa0-2b51c41aa135`: 1,888
  - `6a237335-ff0a-488a-91ba-418dbef07796`: 1,025
  - `1e9ebe91-a507-4ce8-b8dd-40b1f01fa77b`: 829
- **Confirmed this map's own already-documented flat cross-region round-trip
  cost is real and additive, not the sole explanation:** a direct connection
  test against the live `EDGARTOOLS_PROD_MDM` endpoint measured 20 trivial
  `SELECT 1` round trips at 80-198ms each (median ~102ms) — consistent with
  this map's own Notes section (~68ms flat round trip, us-west-2 vs.
  us-east-1 cross-region). This flat cost applies to *every* row regardless
  of candidate-set size; the *additional* multi-hundred-ms cost specifically
  on hyper-refiled entities is the candidate-accumulation problem this
  ticket is about, layered on top of (not instead of) the already-accepted,
  already-out-of-scope round-trip latency.

**Why this isn't Ticket 04's concern:** Ticket 04 fixes commit
*durability/visibility* (how much progress is lost if an oversized group's
processing is interrupted) — it does not, and was never meant to, address
*processing speed*. A group that is slow because a handful of its rows hit
an unusually expensive SELECT scan is unaffected by commit cadence; it's
still slow, just now with bounded data-loss risk instead of unbounded.

**Why concurrency reduction (the user's other live question this session)
doesn't apply here either:** no CPU or lock contention evidence exists at
any level checked (Postgres, ECS). The bottleneck is per-statement latency
on a specific, identifiable minority of entities, not resource contention
concurrency tuning would relieve.

## Answer

**Confirmed live before designing anything:** `_skip_if_unchanged` is not
bypassed by a bug -- the accumulation is legitimate. Live query against the
top accumulator entities showed every single row within a group shares the
exact same `field_value` and `source_system` (one entity: 5,048 rows, 1
distinct value). Each row is a genuinely distinct real transaction
(`source_id`), which migration 012's unique constraint correctly never
collapses (it's keyed on `source_id`, not value) -- "keep only the most
recent N rows" (candidate direction 1 above) was explicitly rejected as
unsafe (an old high-priority row could be truncated away, silently
flipping the winner for `source_priority`/`highest_source_rank`/
`immutable` rules).

**Both a write-time guard and a one-time backfill were built** (user
decision, both needed -- write-time-only leaves already-bloated entities
slow forever; backfill-only recurs on the next run):

- `edgar_warehouse/mdm/survivorship.py`'s `stage_candidate()` gained an
  optional `representative_cache` parameter. When provided (only by
  `MDMPipeline._run_grouped_concurrent`, i.e. `run_securities`/
  `run_persons` -- deliberately NOT `run_companies`' separate per-row
  path, see below), a confirmation of an already-seen `(source_system,
  field_name, field_value, global_priority)` group mutates the tracked
  row in place instead of inserting a new one.
- `edgar_warehouse/mdm/attribute_stage_backfill.py` (new module, mirrors
  `relationship_quarantine_backfill.py`'s dry-run/batch/commit shape): a
  one-time CLI (`mdm collapse-attribute-stage-history --dry-run`) that
  applies the same collapse retroactively to already-accumulated groups.

**A pre-code `/gof-refactor-reviewer` pass caught a real design flaw
before it shipped:** the original plan was a per-call representative
lookup, but `_skip_if_unchanged` already filters out genuinely-reprocessed
rows, so almost every real call reaching `stage_candidate` carries a
brand-new `source_id` -- meaning the exact-match lookup returns `None`
almost every time, and a second per-call lookup would double Postgres
round trips on the *dominant* path, not just the rare heavily-refiled one.
User chose a batch/group-scoped cache over "ship it, measure live." The
final implementation is a lazy, per-group (not eager whole-batch) cache --
`ResolverContext.staged_representatives`, freshly created empty by
`_run_grouped_concurrent` per group, since a group's rows share one
session and process strictly sequentially (safe to hold a live ORM object
across calls, unlike the read-only, cross-thread-shared
`prefetched_source_refs`). Proven live to cost zero extra SQL on a cache
hit within a commit interval, and exactly one reload SELECT (not more)
across a Ticket-04 periodic commit boundary (SQLAlchemy's
`expire_on_commit=True`) -- both directly tested, not assumed.

**The mandatory post-diff 3-axis `/code-review` (not just the pre-code
consult) caught two further real bugs the design review missed:**

1. **Wrong retention rule.** The original design used one lexicographic
   sort ("max effective_date, then max loaded_at as tiebreak") on the
   theory that `_pick_by_rule`'s 4 rule types share one sort key. They
   don't: only `most_recent` looks at `effective_date` at all --
   `immutable`/`highest_source_rank`/`source_priority` sort purely on
   `(priority, loaded_at)` and never touch it. The lexicographic sort
   could silently discard the group's true max-`loaded_at` row (what
   those 3 rule types need) in favor of one with a higher `effective_date`
   but staler `loaded_at` -- flipping the winner for those rule types.
   Fixed in both the write-time cache-miss DB fallback and the backfill:
   retain the most-recently-loaded row, then top up its `effective_date`
   to the group's true max (which may have lived on a different,
   now-collapsed row) -- correct for all 4 rule types on one row, mirrors
   exactly what the write-time incremental fold already does correctly
   (forward-advance `effective_date`, always refresh `loaded_at`).
2. **Stale cache entry on value-changing restage.** The exact-source_id
   restage branch (a literal reprocessing of the same transaction, e.g.
   under `reconciliation_pass`) can change a row's `field_value` without
   telling the cache -- a later brand-new `source_id` confirming the row's
   *old* value would then wrongly reuse (and corrupt) a row that no
   longer represents it. Fixed by popping the stale cache entry when the
   restage branch detects its own key no longer matches the row's new
   value.

Both bugs were reproduced with real regression tests before being fixed
(`test_cache_miss_db_fallback_preserves_both_maxima_from_different_legacy_rows`,
`test_max_effective_date_and_max_loaded_at_on_different_rows_both_preserved`,
`test_restage_with_changed_value_does_not_leave_a_stale_cache_entry`).

29 new tests across `tests/mdm/test_survivorship_representative_collapse.py`
(11) and `tests/mdm/test_attribute_stage_backfill.py` (12), plus the
pre-existing `test_survivorship_stage_upsert.py` (5, unchanged, still
green). Full repo suite: 3250 passed, 7 skipped, only the 8 pre-existing,
already-documented unrelated `tests/integration/
test_acquisition_ledger_postgres.py`/`test_conflict_postgres.py` failures.

**Deployed and backfilled against real prod, 2026-09-11.** Write-time
guard shipped via PR #587 (`edgartools-prod-mdm-large:197`). The backfill
CLI's first real-prod run exposed a second, independent performance bug
not caught by any prior review: `collapse_entity`/`run_backfill` issued
one Postgres round trip per entity for the SELECT and one more **per
collapsed group** for the DELETE (~4.8 groups/entity live-measured), each
a flat ~57ms cross-region round trip -- the real (write) run measured
~2.8 entities/sec against 139,349 candidate entities, projecting ~14h,
and was killed mid-run after 26,500 entities / 160,993 rows deleted
(safe -- it commits every `batch_size`, and a restart's
`find_collapsible_entity_ids` naturally skips already-collapsed entities).

Fixed in PR #588 (`edgartools-prod-mdm-large:198`): new
`collapse_entities_batch()` does one `SELECT ... entity_id IN (...)` and
one bulk `DELETE ... stage_id IN (...)` per whole batch (500 entities)
instead of per-entity/per-group round trips; `collapse_entity()` is now a
thin wrapper over it; `run_backfill()`'s dry-run branch pages at the same
`batch_size` boundary instead of fetching the whole unbounded candidate
list up front (the shape that made the *first* prod dry-run -- pure
correctness validation -- take 2h16m54s on its own). Also added `--limit`
so a future validation pass never needs to repeat that mistake (a
`--dry-run --limit 50` smoke test against the fixed image completed in
4.5s and correctly bounded to 50 entities). Both fixes went through a
pre-code `/gof-refactor-reviewer` consult plus the mandatory post-diff
3-axis `/code-review`, which caught two more real, evidenced issues
before merge: the missing `--limit` flag (Standards axis, against this
repo's own note written earlier the same session) and duplicated
SQL-statement-capture test boilerplate across 3 new tests (GoF axis,
fixed by extracting a local `_capture_statements()` helper). 793 MDM
tests green.

**Live-verified end-to-end, real numbers not estimates:**
- Real-run throughput: ~2.8 entities/sec (unbatched) &rarr; **~87
  entities/sec** (batched), a ~31x speedup. The batched real run finished
  the remaining 112,349 entities in **17m34s** (exit 0), vs. the ~14h the
  unbatched design projected for the full table.
- `mdm_entity_attribute_stage` row count: **2,577,622 &rarr; 1,732,055**
  (measured directly via live Postgres query before and after, across
  both the killed partial run and the completed batched run) -- a delta
  of **845,567 rows**, an exact match to the completed dry-run's
  independently-computed `rows_deleted` prediction (845,567). No drift
  between predicted and actual.

## Not yet specified / open follow-up

- Whether the round-trip-latency figure measured this session (80-198ms
  from this session's own network path) matches the real ECS-task-to-Postgres
  path, or whether it should be re-measured from inside a running ECS task
  for a more authoritative number matching this map's own "real measurements"
  standing preference. Not done in this pass -- the existing ~68ms figure
  already on this map's Notes section, gathered independently, is closer to
  authoritative than this session's opportunistic measurement.
