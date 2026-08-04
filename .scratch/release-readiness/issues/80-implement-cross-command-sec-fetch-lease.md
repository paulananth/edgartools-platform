Type: task
Status: in_progress

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

## Progress (2026-08-04) — Phase 1 (Python + DB layer) done, Phase 2 split off

Reviewed via `advisor` before writing code, which scoped this session's work
down to Phase 1 only (the DB-level lease primitive and its CLI/orchestrator
plumbing) and split the Step Functions wiring across all five state
machines into its own ticket -- [ticket 84](84-wire-sec-fetch-lease-into-state-machines.md)
-- rather than attempting a partial five-state-machine change in one pass.

**Implemented:** `SEC_FETCH_LEASE_NAME = "sec_fetch_active"`
(`warehouse_orchestrator.py`) alongside the existing
`IDENTITY_REFRESH_LEASE_NAME` -- no new DB schema needed, since
`acquire_pipeline_run_lease`/`release_pipeline_run_lease` were already
lease-name-parameterized. New `acquire-sec-fetch-lease`/
`release-sec-fetch-lease` warehouse commands (orchestrator branches, CLI
subparsers, `COMMAND_REGISTRY` entries, `_resolve_scope` entries -- all four
registration points the existing `test_runtime_imports.py` architecture
tests require in sync), deliberately **without** the identity-refresh
lease's backstop/effective-mode machinery (advisor's explicit call --
backstop-overdue priority logic is `daily_identity_refresh`-specific, and
carrying it into this lease would let a deferred SEC-fetch command silently
flip a later command's mode). New path-catalog entry
(`reference.sec_fetch_lease.path`, its own `sec_fetch_lease_path()`
resolver method) so the new lease's `lease_result.json` side-channel can
never collide with the identity-refresh lease's under the same run_id --
flagged by advisor as a real risk (`identity_refresh_lease_path` was
hardcoded to that one lease's template key, not generic).

**Verified, not assumed, before writing any code (advisor's other flagged
risk):** whether release-readiness ticket 79's skip-if-unchanged silver
publish fix could break the *existing* `daily_identity_refresh` lease's
cross-run durability, since its only local write
(`db.acquire_pipeline_run_lease`) touches `pipeline_run_lease`, a table
also listed in `EXCLUDED_OPERATIONAL_TABLES`. Traced the actual merge code:
`pipeline_run_lease` is *also* independently registered in
`PROTECTED_TABLE_REGISTRY` (`silver_protection.py:231-232`,
`business_keys=("lease_name",)`, `authority_column="updated_at"`), and
`merge_candidate_into_canonical`'s merge loop iterates
`PROTECTED_TABLE_REGISTRY` unconditionally -- registry membership wins, so
every lease acquire/release is a real content change ticket 79's
`compute_silver_fingerprint` always detects, and the full merge/publish
always still runs. Ticket 79 does not regress the identity-refresh lease.
This finding is recorded on both tickets so neither has to re-derive it.

**Test plan items 1-3 done and green** (`tests/unit/test_sec_fetch_lease.py`,
7 tests): exclusive acquisition (a second command genuinely can't acquire
while the first holds it, and can't release under the wrong run_id),
staleness reclaim (20h default, matching the identity-refresh lease's own
coverage), a crashed-holder case (acquired, never released, still correctly
denies a fresh acquirer -- proving a crash never looks like a clean
release), the orchestrator command's S3 side-channel write on both the
acquired and deferred paths, the release command freeing the lease, and an
explicit independence check that holding one lease never blocks the other.
Full suite (`tests/unit`+`tests/application`+`tests/architecture`+`tests/mdm`):
1721 passed, 4 skipped, 35 subtests passed, one pre-existing unrelated
`AWS_PROFILE`-dependent `test_go_live_wizard.py` failure (same one noted on
tickets 75/76/79/81).

**Not done (deliberately split to ticket 84, per advisor):** nothing
acquires or releases this lease yet -- the five SEC-fetching state
machines' Step Functions definitions are unchanged, so mutual exclusion is
implemented but not yet enforced in prod. Test plan item 4 (live
confirmation two commands can't run concurrently) can't be exercised until
ticket 84 lands.

**Incident note:** this ticket's Phase 1 code was accidentally reverted
mid-session by a `git checkout main -- .` run while still on the
ticket-79 branch (the same dangerous-command class flagged earlier this
session) -- caught immediately via a post-command sanity grep, recovered
in full from conversation context (nothing was guessed), and confirmed
byte-for-byte via the identical full-suite result (1721 passed) before and
after. No data was actually lost.
