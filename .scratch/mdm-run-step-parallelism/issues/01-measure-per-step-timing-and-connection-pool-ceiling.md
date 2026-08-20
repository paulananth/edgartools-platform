# 01 — Measure Per-Step Timing and Connection-Pool Ceiling

Labels: wayfinder:task

**Blocked by:** None — can start immediately.

**Status:** resolved (2026-08-19)

## Question

What does a real, complete breakdown of `mdm run --entity-type all`'s five
resolution steps (company, adviser, security, person, fund) actually cost in
wall-clock time today, run against the current live silver dataset — and
what is the safe upper bound on how many of those steps' internal worker
pools (`MDM_RESOLVE_CONCURRENCY`, default 16/domain, per the
mdm-run-throughput map) can run concurrently against MDM Postgres without
exceeding `MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW` (both default 15) or
otherwise degrading badly under the ~68ms-per-round-trip cross-region
latency floor already established by that map?

Concretely:

- [ ] Real, complete (not truncated by a monitor timeout) durations for each
      of the five `--entity-type` steps, run standalone (as this session did
      for `person`, which took ~1m55s) or extracted from a recent `--entity-
      type all` execution's logs if a clean one exists. Note the live
      in-progress data point already captured in the map (`security` still
      running past 25 minutes as of chartering) — get this to a real
      completed number, not an estimate.
- [ ] `run_advisers`/`run_funds` timings specifically — they're already
      bulk/batched (out of scope for mdm-run-throughput's per-row fix), so
      confirm whether they're already fast enough that overlapping them with
      the other three buys negligible wall-clock benefit.
- [ ] The actual row counts each step processed during the measurement (from
      `mdm counts`/pipeline stats), so a duration number is interpretable
      against how much work it represents, not just a bare timestamp diff.
- [ ] A concrete connection-pool budget calculation: today's
      `MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW` were sized assuming one
      step's worker pool active at a time (per mdm-run-throughput's own
      sizing note: "16 workers + the pipeline's own primary session doesn't
      exceed the old... 5+10=15"). If N steps ran concurrently, each
      wanting up to 16 workers, what actually happens — pool exhaustion,
      queueing/blocking, or does SQLAlchemy's pool just serialize excess
      requests gracefully? Test or reason from the pool implementation,
      don't guess.
- [ ] Whether the MDM Postgres instance itself (Snowflake-hosted, per
      CLAUDE.md's "MDM database" note) has any documented or observable
      connection/session ceiling independent of the application-side pool
      config, that a 5x-larger concurrent worker count could hit.

## Answer

**Resolved (2026-08-19).** Five standalone `--entity-type` runs, launched
against the same live silver dataset within the same session (`person`
measured first while charting the map; `company`/`adviser`/`fund`/`security`
launched together immediately after):

| Entity type | Duration | Rows processed | ms/row | Notes |
|---|---|---|---|---|
| `adviser` | **31s** (`duration_ms: 31000`) | — (bulk) | — | `adv_bulk.py`, no internal worker pool, batched INSERTs |
| `fund` | **53s** (`duration_ms: 52896`) | — (bulk) | — | same shape as adviser |
| `person` | ~1m55s (115s) | — | — | measured while charting the map, not re-captured with a row count |
| `security` | **1h50m31s** (6,630.65s, `duration_ms: 6630652`) | **20,683 securities** | ~321ms/row | per-row `ThreadPoolExecutor`, 16 workers |
| `company` | **2h14m7s** (8,046.71s, `duration_ms: 8046712`) | **67,870 companies** | ~119ms/row | per-row `ThreadPoolExecutor`, 16 workers |

**Headline finding: the five steps are wildly asymmetric, not close to an
even split.** The two bulk/batched steps (`adviser`, `fund`) are
essentially free (tens of seconds) regardless of their large raw row
counts (234K ADV filings, 1.58M private funds) — confirming
mdm-run-throughput's decision to leave them out of its per-row concurrency
fix; overlapping them with anything else buys at most ~53s of wall-clock
savings. `security` and `company` are the real cost — **over an hour each**,
combined ~4h05m if run sequentially (which is exactly what `run_all()` does
today, back to back, on top of the ~1m24s bulk/batched steps and whatever
`person` and relationship derivation add).

**Secondary finding (out of this ticket's scope, flagged for whoever picks
it up next, not chased further here):** `company`'s 67,870-row run only
grew `mdm_company`'s total row count by ~63 (67,807 at this session's
earlier `mdm counts` check, 67,870 after) — meaning **~99.9% of this run's
8,046s was spent re-verifying already-resolved companies**, not resolving
new ones. Commit `7ffda2d7` (the same commit whose migration gap caused
the earlier schema-drift incident this session) added a "skip-if-unchanged
fast path" to `run_companies` specifically to avoid paying full cost on
unchanged rows — this run's ~119ms/row average suggests that fast path may
not be avoiding the real work it was meant to, or at least isn't visible
in this coarse a measurement. Worth a look before or alongside ticket 02,
since a working skip-fast-path could shrink `company`'s real number far
more than any parallelism shape would.

This directly shapes ticket 02: the real prize is whether `company` and
`security` can usefully overlap **each other** (not `adviser`/`fund`,
which are already negligible) — and given each already saturates its own
16-worker budget against the same ~68ms-round-trip-latency Postgres
instance (mdm-run-throughput's root cause), running both simultaneously
may mean contending for the same underlying latency/connection budget
rather than a clean 2x wall-clock win. The connection-pool math below
quantifies that risk.

**Connection-pool ceiling analysis (code-grounded, not measured live):**

- `edgar_warehouse/mdm/database.py`: `get_engine()` builds a **fresh**
  `Engine` on every call (`create_engine(url, **kwargs)`, no caching/
  memoization) with `pool_size=15` + `max_overflow=15` = **30 total
  connections** per engine instance (`MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW`,
  both default `15` — the file's own comment: "sized for up to ~20
  concurrent workers with headroom for the primary session").
- Today, one `mdm run` CLI invocation creates **exactly one** engine/session
  at entry (`edgar_warehouse/mdm/cli.py` ~line 484-485,
  `get_session(get_engine())`), passed into one `MDMPipeline` instance and
  reused sequentially across all five `run_*` calls. Each of
  `run_companies`/`run_securities`/`run_persons` independently opens its own
  bounded `ThreadPoolExecutor` (`_RESOLVE_MAX_WORKERS`, default 16 via
  `MDM_RESOLVE_CONCURRENCY`, per-domain override available) whose workers
  each pull a session from this **same shared pool** — but only one of the
  three runs at a time today, so peak demand is ~16 workers + 1 primary
  session = 17, comfortably under the 30-connection ceiling.
  `run_advisers`/`run_funds` (`edgar_warehouse/mdm/adv_bulk.py`) have **no**
  internal `ThreadPoolExecutor** at all — sequential chunked bulk INSERTs
  (`_WRITE_BATCH_SIZE=5000`) on the one primary session — so they add
  negligible (~1 connection) demand regardless of parallelism shape.
- **In-process concurrency scenario** (one ECS task, all steps share the
  one engine): if `company`+`security`+`person` ran concurrently, worst-case
  simultaneous demand is ~3×16 workers + 3 sessions ≈ **51 connections**
  against the current 30-connection ceiling — over-subscribed ~1.7x.
  SQLAlchemy's `QueuePool` does not hard-fail on this: excess checkout
  requests block/queue (default `pool_timeout=30s`) rather than erroring
  immediately, so the realistic failure mode is increased queueing/
  contention, not a crash — but the pool would need re-tuning
  (`MDM_DB_POOL_SIZE`/`MDM_DB_MAX_OVERFLOW` raised) to actually realize a
  3-way overlap rather than just serializing through a smaller effective
  slot count than the app-level thread count suggests.
- **Multi-task scenario** (Step Functions `Parallel`, one ECS task per
  entity type): each task calls `get_engine()` independently, so each gets
  its **own** isolated 30-connection pool — no risk of one step's pool
  exhaustion starving another's checkouts (unlike the shared-engine
  in-process case). Worst-case simultaneous app-side connections across
  `company`+`security`+`person` tasks: ~3×17 ≈ 51, same total demand as the
  in-process case, just isolated into 3 separate 30-slot pools instead of
  one shared 30-slot pool — meaningfully safer from a contention-blocking
  standpoint, at the cost of needing 3x the pool headroom provisioned
  overall if the Postgres server itself has a hard ceiling (see next point).
- **MDM Postgres server-side `max_connections`: not established.** No
  documentation in `infra/scripts/bootstrap-prod-mdm.sh` or elsewhere in
  this repo records the Snowflake-hosted Postgres instance's connection
  ceiling, and this session's tooling (the `mdm` CLI's subcommands) doesn't
  expose a way to run `SHOW max_connections` or equivalent. **Genuine gap,
  not a guess** — whoever resolves ticket 02 should get this number via a
  direct Postgres client connection before committing to a shape that could
  push app-side connections into the 50-90+ range.

**Remaining open item, carried to ticket 02:** the MDM Postgres server-side
`max_connections` figure above was not established — flagged as a genuine
gap, not guessed at. Whoever resolves ticket 02 should get this number via
a direct Postgres client connection before committing to a shape that could
push app-side connections into the 50-90+ range.
