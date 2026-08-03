Type: task
Status: open

## Question

Implement [pipeline-throughput-architecture ticket 09](../../pipeline-throughput-architecture/issues/09-decide-cross-command-sec-fetch-mutual-exclusion.md)'s
decision: a shared `pipeline_run_lease` (new lease name, e.g.
`sec_fetch_active`) that every SEC-fetching command acquires before its
fetch-heavy phase, so only one command's worth of SEC request traffic
runs platform-wide at a time.

## Why this is urgent, not just a nice-to-have

Confirmed via real execution history, not assumption: `bootstrap` and
`daily-incremental` actually overlapped for **4.16 hours** in prod on
2026-07-30 -- both independently making SEC calls, both jointly over
SEC's stated 10 req/sec aggregate ceiling for that window. This has
already happened once; nothing currently prevents it happening again.

## Decision already made (ticket 09)

- **Hard mutual exclusion**, not a shared rate budget -- reuse the
  existing `pipeline_run_lease` primitive (`silver_store.py:2707`,
  already proven for `daily_identity_refresh`), don't build new
  distributed rate-limiting infrastructure.
- **Scope**: the 5 commands sharing SEC-fetching code paths --
  `daily_incremental`, `bootstrap`, `bootstrap_full`, `targeted_resync`,
  `bootstrap_batch` (same 5 identified in
  [ticket 78](78-implement-shared-submissions-fetch-concurrency.md)).
- **Accepted tradeoff**: an operator running one SEC-fetching command
  while another is mid-run will have to wait for the lease. Explicitly
  judged acceptable against the compliance risk.

## Implementation needs (not fully specified in the decision -- design
during implementation)

1. **New lease name** (`sec_fetch_active` or similar) registered
   alongside `IDENTITY_REFRESH_LEASE_NAME` in
   `warehouse_orchestrator.py`.
2. **Acquire/release boundary**: decide whether the lease wraps the whole
   command's lifetime or just its SEC-fetch-heavy phase, mirroring how
   `daily_identity_refresh`'s lease already scopes narrowly to
   `ComputeIdentityRefreshWindow`/`ReduceIdentityRefresh` rather than all
   of `daily-incremental`. Wrapping only the fetch phase is likely lower
   operational cost (less time other commands wait) but needs the same
   care `daily_identity_refresh` took to get right.
3. **Wait/retry semantics** when the lease is held: block-and-poll
   (mirroring the existing `AcquireLease`/`ReadLeaseResult` Step
   Functions state pattern) vs. fail-fast-and-let-Step-Functions-retry.
   Check how long `AcquireLease` currently takes for
   `daily_identity_refresh` in practice (observed live this session:
   roughly 3 minutes) before picking a pattern for a lease that could be
   held for hours by another command's full SEC-fetch phase.
4. **Staleness reclaim**: reuse `acquire_pipeline_run_lease`'s existing
   configurable staleness window (20h default) -- verify this default is
   still appropriate for the new lease's expected hold duration (a
   `bootstrap` full-universe run could plausibly hold it longer than
   `daily-incremental`'s own identity-refresh lease ever does).
5. **`bootstrap_batch`'s specific wiring**: since it's a Distributed Map
   fan-out (`BOOTSTRAP_BATCH_CONCURRENCY` concurrent tasks within one
   `load_history` execution), the lease needs to be acquired once at the
   `load_history`/`bootstrap-batch` orchestration level, not per
   concurrent task -- otherwise the concurrent tasks would contend with
   *each other* for the same lease, which is not what this ticket is
   solving (that's ticket 06's already-separate concern).

## Test plan

Real DB-backed tests (per this workstream's established discipline):
1. **Contention test**: two commands attempting to acquire the same lease
   -- assert the second genuinely waits/fails until the first releases,
   not a race where both proceed.
2. **Staleness reclaim test**: a lease held past its staleness window is
   reclaimable by a new run, matching `daily_identity_refresh`'s existing
   coverage.
3. **Release-on-failure test**: a command that fails mid-run releases (or
   times out and gets reclaimed) rather than wedging the lease
   permanently -- mirror `daily_identity_refresh`'s existing
   release-on-failure handling.
4. **Live measurement**: deliberately trigger two of the 5 commands with
   overlapping schedules in a non-prod-impacting way (or carefully in
   prod during a low-traffic window) and confirm the second genuinely
   waits rather than running concurrently.

## Done when

Implemented, all test cases passing, full suite green, live confirmation
that two SEC-fetching commands can no longer run concurrently.
