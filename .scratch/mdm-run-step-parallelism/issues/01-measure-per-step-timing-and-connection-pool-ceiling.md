# 01 — Measure Per-Step Timing and Connection-Pool Ceiling

Labels: wayfinder:task

**Blocked by:** None — can start immediately.

**Status:** in-progress (claimed 2026-08-19)

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

<!-- filled in on resolution -->
