Type: task
Status: open

## Question

[Ticket 80](80-implement-cross-command-sec-fetch-lease.md)'s Phase 1 (the
`sec_fetch_active` `pipeline_run_lease` row, `acquire-sec-fetch-lease`/
`release-sec-fetch-lease` warehouse commands, and their `lease_result.json`
S3 side-channel) is implemented and DB-tested, but nothing calls those
commands yet. This ticket wires them into the five SEC-fetching state
machines' Step Functions definitions
(`infra/scripts/deploy-aws-application.sh`) so the lease actually enforces
mutual exclusion in prod: `daily_incremental`, `bootstrap`, `bootstrap_full`,
`targeted_resync`, `bootstrap_batch`.

## Why this is split from ticket 80's Phase 1

Per advisor review during Phase 1: this is the actual hard part (five
separate state machine shapes, each needing its own acquire/release
placement, not one uniform template) and deserves its own scoped session
rather than a partial, half-wired change. `daily_identity_refresh`'s
existing lease wiring (`deploy-aws-application.sh:2543-2702`) is the
reference pattern -- `AcquireLease`/`ReadLeaseResult`/`LeaseAcquiredCheck`/
`Deferred`/`ReleaseLease`/`ReleaseLeaseFailedNonFatal` states -- but it
wraps exactly one state machine's Stage 0/reduce phase, not five
differently-shaped machines with a fan-out concern (`bootstrap_batch`)
none of the identity-refresh precedent has to handle.

## Verified during Phase 1 (don't re-derive)

- `pipeline_run_lease` is dual-registered: in `PROTECTED_TABLE_REGISTRY`
  (`silver_protection.py:231-232`, `business_keys=("lease_name",)`,
  `authority_column="updated_at"`) *and* `EXCLUDED_OPERATIONAL_TABLES`.
  `merge_candidate_into_canonical`'s merge loop iterates
  `PROTECTED_TABLE_REGISTRY` unconditionally, so registry membership wins --
  every acquire/release genuinely merges into and survives in canonical
  silver.duckdb. Confirmed this means [ticket 79](79-implement-skip-noop-silver-publish.md)'s
  skip-if-unchanged fix does **not** regress the existing
  `daily_identity_refresh` lease (a real concern raised and checked before
  writing any Phase 1 code, not assumed) -- any lease acquire/release always
  changes `compute_silver_fingerprint`'s protected-table content, so the
  full merge/publish always still runs whenever a lease command runs.
- The lease's actual cross-run durability is the `pipeline_run_lease` DB row
  surviving via the ordinary silver merge/publish path -- `lease_result.json`
  (bronze, per-run_id) is a separate, additional side-channel that exists
  *only* because `ecs:runTask.sync` can't surface a container's app-level
  stdout/metrics to a Step Functions Choice state; it is not itself the
  durable cross-run record. Both must be written by the acquire command
  (already true for both the existing identity-refresh lease and the new
  `sec_fetch_active` lease).

## Open design questions (ticket 80's own text, not yet resolved)

1. **Acquire/release boundary**: whole command lifetime vs. just the
   SEC-fetch-heavy phase. `daily_identity_refresh`'s lease already narrows
   to `ComputeIdentityRefreshWindow`/`ReduceIdentityRefresh`, not all of
   `daily-incremental` -- likely the right model here too (e.g. wrap only
   the artifact-fetch/submissions-fetch phases ticket 77/78 optimized, not
   gold-refresh/MDM stages that don't call SEC at all), but needs the same
   per-state-machine care, not a blanket wrap-everything default.
2. **Wait/retry semantics**: block-and-poll (`AcquireLease`/
   `ReadLeaseResult` pattern) vs. fail-fast-and-retry. The identity-refresh
   lease is typically held ~3 minutes (observed live); a SEC-fetch lease
   could plausibly be held for hours (a full `bootstrap` run). A Choice-state
   `Deferred` terminal (today's identity-refresh pattern) may not be the
   right operator experience for an hours-long wait -- needs a decision, not
   a default copy of the existing pattern.
3. **Staleness window**: `acquire_pipeline_run_lease`'s 20h default was
   sized against the Identity Backstop Sweep's 18h completion bound. Verify
   it's still the right ceiling for the longest-running of the five
   SEC-fetching commands (a full-universe `bootstrap` run) before reusing it
   unchanged.
4. **`bootstrap_batch` fan-out**: it runs as a Distributed Map
   (`BOOTSTRAP_BATCH_CONCURRENCY` concurrent tasks within one `load_history`
   execution). The lease must be acquired once at the `load_history`
   orchestration level, before the Map starts, not per concurrent task --
   otherwise the Map's own tasks would contend with *each other* for the
   same lease, which is a different, already-separately-solved concern
   (`BOOTSTRAP_BATCH_CONCURRENCY`, ticket 06).

## Test plan (from ticket 80, still applicable)

4. **Live measurement**: deliberately trigger two of the five commands with
   overlapping schedules (carefully, in a low-traffic window) and confirm
   the second genuinely waits rather than running concurrently -- the one
   test plan item Phase 1 didn't and couldn't cover (no SFN wiring yet to
   exercise).

## Done when

Lease acquire/release wired into all five state machines at a deliberately
chosen boundary, wait/retry semantics decided (not defaulted), staleness
window re-verified, `bootstrap_batch`'s single-acquisition-per-Map wiring
confirmed correct, and a live overlapping-trigger test confirms the second
command genuinely waits.
