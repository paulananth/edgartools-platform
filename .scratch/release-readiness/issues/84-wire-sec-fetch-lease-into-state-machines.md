Type: task
Status: in_progress

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

## Decisions (resolved via grilling, 2026-08-04)

1. **Lease boundary**: fetch-heavy phases only, not whole command lifetime
   -- matches `daily_identity_refresh`'s narrow-lease precedent's *spirit*
   (see the "5th machine" correction below for where that precedent's own
   actual scope was mischaracterized mid-session).
2. **Wait/retry semantics**: defer-and-terminate, not a new polling loop.
   Corrected mid-grilling: the existing identity-refresh lease's `Deferred`
   state is `"End": true` -- it does **not** poll/retry within one
   execution, it relies on the *next scheduled trigger* (daily_incremental's
   own EventBridge schedule). For the other 4, ad-hoc/operator-triggered
   commands: defer-and-terminate too, relying on the operator re-triggering
   -- matches how these commands are already operated (no auto-retry exists
   for their failures either).
3. **Staleness window**: 16h, not the identity-refresh lease's 20h default.
   Sized against real measured prod runtimes queried live via
   `aws stepfunctions list-executions` (not guessed): `bootstrap` ~4h10m
   (2026-07-30, the same run ticket 09's 4.16h overlap finding came from),
   `daily_incremental` ~7h7m (2026-08-03, the ticket-74 repair-verify run;
   `targeted_resync`/`bootstrap_batch`/`load_history` had zero completed
   executions to measure from). An initial 8h proposal was revised after
   this measurement showed daily_incremental's own real runtime left only
   ~53 minutes of margin -- 16h gives ~2h40m margin over the worst
   documented related-pipeline run (13h20m, CLAUDE.md's pre-fix daily
   accession-expansion case), same bound-plus-margin reasoning as the
   existing 18h/20h identity-refresh pair.
4. **5th machine scope (corrected mid-session)**: this ticket's own text
   named `bootstrap_batch` as the 5th SEC-fetching command with a
   Distributed-Map fan-out concern living inside `load_history`. That
   description was **stale relative to the actual code**: `load_history`
   (`write_load_history_definition`) was restructured at some prior point
   from the original parallel `bootstrap-batch ×N` Map into a **sequential**
   (`MaxConcurrency=1`) windowed `bootstrap-next` pipeline -- the deploy
   script's own "Phased pipeline" comment documents this replacement. The
   real parallel `bootstrap-batch ×N` (`BOOTSTRAP_BATCH_CONCURRENCY`)
   fan-out this ticket described lives in a **separate**, still-deployed
   standalone state machine (`write_bootstrap_batched_definition`,
   registered as `bootstrap_batched`) that is not mentioned anywhere in
   CLAUDE.md's user-facing "When to use what" table. Two other machines
   (`silver_mdm_gold`, `bronze_seed_silver_gold`) also invoke the
   `bootstrap-batch` CLI command, mostly with `--artifact-policy skip` (an
   explicit zero-SEC-calls invariant -- no lease needed for that path), plus
   `bronze_seed_silver_gold` has one additional strict-candidate path
   (`--artifact-policy all_attachments`, ticket-20-related) that does make
   real SEC calls. **Decided (user, explicit)**: wire `load_history` itself
   only for this ticket -- it's CLAUDE.md's actual recommended bulk-load
   entry point and still makes real SEC calls, no fan-out concern remains
   since it's sequential now. The standalone `bootstrap_batched` machine and
   `bronze_seed_silver_gold`'s strict-candidate path are **out of scope**
   here -- see "Not yet specified" below.

## Progress (2026-08-04)

All 4 machines in the corrected scope are wired, following the identical
acquire-before-fetch-phase / release-before-MdmRun shape (each state
machine builds its own copy of a `build_sec_fetch_lease_states` factory --
these are separate `python3 -` subprocess heredocs and can't share code
directly, an existing convention in this file):

- **`daily_incremental`/`bootstrap`** (`write_warehouse_mdm_gold_definition`,
  shared function): acquire after the existing identity-refresh lease's
  `ApplyEffectiveRefreshMode` (daily_incremental) / before `SeedUniverse`
  (bootstrap); release before `MdmRun`, with every ADV/firm-roster
  fetch-chain `Catch` retargeted to release the lease before falling
  through instead of skipping release on failure. The two leases
  (identity-refresh, sec_fetch_active) are independent and coexist --
  identity-refresh still spans the whole `daily_incremental` run;
  sec_fetch_active spans only the SEC/IAPD-calling sub-span within it.
- **`bootstrap_full`/`targeted_resync`** (`write_single_workflow_definition`,
  shared with 5 other non-SEC-fetching workflows in the same loop): new
  `wrap_with_sec_fetch_lease` parameter, `true` only for these two at the
  call site. No operator-alert notification for either shared function's
  ad-hoc branches -- only `daily_incremental` gets one (the sole unattended
  scheduled command among the 5).
- **`load_history`** (`write_load_history_definition`): acquire before
  `SeedUniverse`, release before `MdmRun` -- spans `SeedUniverse`,
  `MdmSeedUniverse`, `Stage0CompanyIdentity`, `Stage1Parallel`/`Stage1B*`,
  and the ADV/firm-roster chain in one acquire/release, no fan-out wiring
  needed per the corrected scope above.

Also fixed a plumbing gap found while implementing: `acquire-sec-fetch-lease`
(`warehouse_orchestrator.py`) was calling `acquire_pipeline_run_lease`
without `stale_after_seconds`, silently falling through to its 20h default
instead of the intended 16h -- added `SEC_FETCH_LEASE_STALE_AFTER_SECONDS`
and threaded it through, with a regression test proving the 16h boundary
(not 20h) is actually in effect.

**Tests**: 1 new unit test (16h-vs-20h plumbing), 1 new architecture test
file for `bootstrap_full`/`targeted_resync` (4 tests), ~10 new/updated
tests in the existing `daily_incremental`/`bootstrap` architecture test
files, 4 new tests plus fixes to 12 pre-existing tests in
`test_load_history_state_machine.py` (mostly retargeting `Next`/`Catch`
assertions from `MdmRun` to `ReleaseSecFetchLease`, and adding
`SecFetchLeaseAcquiredCheck` to the trace helpers' preferred-choice maps),
plus 3 more tests (one per generated-definition source) tying
`ReadSecFetchLeaseResult`'s hand-typed S3 key to the real
`sec_fetch_lease_path()` resolver -- found via advisor review to be an
uncovered gap identical to a guard the identity-refresh lease already has;
`ReadSecFetchLeaseResult` deliberately has no Catch, so a drifted key would
hard-fail every SEC-fetching command's execution on first run after a
`.properties` change, not just defer. Full suite
(`tests/unit tests/application tests/architecture tests/mdm`) green both
times this was checked mid-implementation, with only the one pre-existing
unrelated `test_go_live_wizard.py` failure. All 5 generated definitions
also validated clean (`result: OK`, zero diagnostics) via
`aws stepfunctions validate-state-machine-definition` against real AWS.

**Blast-radius note (advisor review, not a defect):** a hard failure in a
strict, Catch-less stage inside the fetch-heavy span (`ComputeWindows`,
`Stage0CompanyIdentity`/`Stage0CompanyIdentityBounded`, Branch A
`WindowedBootstrap`) terminates the execution with `sec_fetch_active` still
held -- release is best-effort by design (matching the identity-refresh
lease's own documented convention), so the 16h stale-reclaim window is the
actual recovery path, same as before. What's different from the identity-
refresh lease: a wedge here blocks **all five** SEC-fetching commands
platform-wide, not just one command's own next scheduled run. If an
operator ever sees `daily_incremental` (or any of the other 4) deferred
unexpectedly, check for a stuck/failed run holding `sec_fetch_active` first
(`SELECT * FROM pipeline_run_lease WHERE lease_name = 'sec_fetch_active'`)
before assuming a scheduling issue.

**Not yet done**:
- Test plan item 4 (live overlapping-trigger test: deliberately trigger two
  of the 5 commands with overlapping schedules and confirm the second
  genuinely defers) -- needs a deploy + a carefully-timed live trigger,
  deferred pending explicit confirmation per this workstream's
  live/destructive-action convention.
- `bootstrap_batched` (the real Distributed-Map `bootstrap-batch ×N`
  machine) and `bronze_seed_silver_gold`'s strict-candidate path remain
  unwired -- see "Not yet specified" below for the follow-up.

## Not yet specified

Whether `bootstrap_batched` (the standalone Distributed-Map state machine,
not `load_history`) and `bronze_seed_silver_gold`'s strict-candidate
(`--artifact-policy all_attachments`, ticket-20-related) path need
`sec_fetch_active` too. Both make real SEC calls outside the 4 machines this
ticket wired. `bootstrap_batched` isn't referenced in CLAUDE.md's
user-facing "When to use what" table, so its current operational status
(actively used, or superseded by `load_history` and left deployed) needs
establishing before deciding whether wiring it is worth the same
per-machine care ticket 84 applied here -- including its genuine
`BOOTSTRAP_BATCH_CONCURRENCY`-concurrent Map fan-out, which is the actual
"acquire once before the Map, not per task" concern this ticket's original
text anticipated but, per the correction above, doesn't apply to
`load_history` after all.
