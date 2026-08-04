Type: task
Status: resolved

## Question

Ticket 84 wired `sec_fetch_active` (the cross-command SEC-fetch lease) into
all 5 SEC-fetching state machines, but the actual work state --
`RunWarehouseTask` (and its `RunWarehouseTaskDefault`/
`RunWarehouseTaskWithCikList` variants in `targeted_resync`) -- has no
`Catch`. This was known and documented in ticket 84 as a "blast-radius
note," treated as an accepted tradeoff matching the existing
identity-refresh lease's own convention (release is best-effort; the 16h
stale-reclaim window is the real recovery path).

Live verification of ticket 84 (2026-08-04) empirically demonstrated this
is a live, easily-triggered problem, not a theoretical edge case: **two
separate, unrelated, completely mundane failures** (a real immutable-bronze
content conflict on a real CIK, and a deliberately-invalid CLI arg used in
a follow-up probe) both wedged `sec_fetch_active` on the first try, each
time requiring a manual `ecs run-task` + `release-sec-fetch-lease
--run-id <holder>` to recover. Any `RunWarehouseTask` failure -- SEC rate
limiting, a transient S3 error, a bad filing, an ECS capacity blip --
wedges **all 5 SEC-fetching commands platform-wide** for up to 16h, not
just the one command that failed.

This repo already has the exact fix pattern in the same file:
`adv_bulk_fetch_catch = [{"ErrorEquals": ["States.ALL"], "ResultPath": None,
"Next": "ReleaseSecFetchLease"}]`, applied to `fetch-adv-bulk`/
`ingest-relationship-sources` inside `write_warehouse_mdm_gold_definition`.
The same `Catch` needs to route `RunWarehouseTask` (and its two
`targeted_resync` variants) to `ReleaseSecFetchLease` in all 5 machines,
so a downstream task failure releases the lease before the execution fails,
instead of leaving it held.

**Decisions to confirm before implementing** (not yet resolved):
- Should the `Catch` re-raise the original failure after releasing (so the
  execution still shows FAILED, just without wedging the lease), or should
  it route to a distinct terminal "released, but underlying task failed"
  state? The existing `adv_bulk_fetch_catch` pattern continues past the
  failure into a non-fatal path (`ReleaseSecFetchLease` -> success) rather
  than re-failing -- confirm whether that's the right shape for a
  `RunWarehouseTask` failure too, since callers/alerting may currently
  depend on execution status reflecting whether the real work succeeded.
- Does this change interact with `RunWarehouseTask`'s existing `Retry`
  block (2 attempts, `States.TaskFailed`)? The `Catch` should only fire
  after retries are exhausted, which is already how Step Functions orders
  `Retry` before `Catch` -- just confirm no `MaxAttempts` interaction
  changes semantics for the 5 machines' individually-tuned retry configs.

## Decisions (resolved via AskUserQuestion, 2026-08-04)

- **Scope vs. identity-refresh lease**: confirmed via investigation that
  `ReduceIdentityRefresh` (the identity-refresh lease's own core work
  state) has the exact same "no Catch" shape live in prod -- this is the
  codebase's existing, deliberate convention, not a unique ticket-84
  oversight. Decided anyway: fix `sec_fetch_active` only, not
  identity-refresh too. Justification: `sec_fetch_active` is shared across
  all 5 SEC-fetching commands, so a wedge blocks all 5 platform-wide;
  identity-refresh only blocks its own next `daily_incremental` run. The
  asymmetric blast radius justifies asymmetric failure handling even
  though today's code treats both leases identically.
- **Fail semantics**: release, then still fail the execution (not silently
  succeed like `adv_bulk_fetch_catch`'s existing pattern does for
  ADV/firm-roster). A `RunWarehouseTask`-class failure means the actual
  core work didn't happen -- silently reporting success would suppress
  `ExecutionsFailed`/CloudWatch alarm visibility for a real failure.
  Implemented as: `Catch` (`ResultPath: $.sec_fetch_task_error`) ->
  `ReleaseSecFetchLeaseAfterFailure` (release-sec-fetch-lease, itself
  Catch-wrapped so a release failure still reaches the next state) ->
  `SecFetchTaskFailed` (`Type: Fail`, `ErrorPath`/`CausePath` surfacing
  the original caught error). Distinct from the existing
  `ReleaseSecFetchLease`/`ReleaseSecFetchLeaseFailedNonFatal` pair (the
  happy-path release, unchanged, still ends in success).
- **Scope of states, not just "RunWarehouseTask"**: discovered mid-session
  that only `bootstrap_full`/`targeted_resync` have a single
  `RunWarehouseTask`-shaped state in their fetch-heavy span.
  `bootstrap`/`daily_incremental`/`load_history` have several -- up to 8
  for `load_history`. Confirmed via `AskUserQuestion` (expanded scope
  preview shown before implementing): fix every currently-uncaught
  Task/Map state in the span, not just the literally-named
  `RunWarehouseTask`. Final list:
  - `bootstrap_full`/`targeted_resync`: `RunWarehouseTask` /
    `RunWarehouseTaskDefault` / `RunWarehouseTaskWithCikList`.
  - `bootstrap`: `SeedUniverse`, `RunWarehouseTask`.
  - `daily_incremental`: `ComputeIdentityRefreshWindow`,
    `ComputeIdentityBackstopUniverse`, `Stage0CompanyIdentityBounded`,
    `ReduceIdentityRefresh`, `RunWarehouseTask`.
  - `load_history`: `SeedUniverse`, `MdmSeedUniverse`, `ComputeWindows`,
    `Stage0CompanyIdentity`, `Stage1Parallel`.
  Deliberately **excluded**: `FetchAdvBulk`/`FetchAdvBulkForced`/
  `IngestAdvBulkSources`/`FetchFirmRoster`/`FetchFirmRosterForced`/
  `IngestFirmRosterSources` (already had `adv_bulk_fetch_catch`, unchanged
  -- that catch continues forward and still reaches `ReleaseSecFetchLease`
  on the happy path, so it was never actually uncaught) and
  `load_history`'s `Stage1BEntityFacts`/`Stage1BPerFiling`/
  `Stage1BThirteenF` (AD-13's deliberate lenient-catch-and-continue
  pattern, same "still reaches ReleaseSecFetchLease" reasoning -- verified
  by checking their live JSON for an existing `Catch` before assuming they
  needed the fix, since two existing tests
  (`test_stage0_company_identity_is_strict_not_lenient` in both
  `test_load_history_state_machine.py` and
  `test_daily_incremental_state_machine.py`) explicitly assert
  `Stage0CompanyIdentity(Bounded)` must stay strict, not lenient -- both
  updated to assert the Catch routes to `SecFetchTaskFailed` (still a hard
  abort) rather than to any "proceed anyway" state).

## Progress (2026-08-04)

Implemented across all 3 factory functions in
`infra/scripts/deploy-aws-application.sh`
(`write_single_workflow_definition`, `write_warehouse_mdm_gold_definition`,
`write_load_history_definition`) -- each got its own `Catch`-attaching
helper (can't share code directly, each factory is its own `python3 -`
subprocess) plus the shared `ReleaseSecFetchLeaseAfterFailure`/
`SecFetchTaskFailed` state pair added to each's `build_sec_fetch_lease_states`
return dict.

10 new/updated architecture tests across
`test_sec_fetch_lease_single_workflow_wiring.py`,
`test_daily_identity_refresh_state_machine.py`,
`test_load_history_state_machine.py`. Full suite
(`tests/unit tests/application tests/architecture tests/mdm`): 1749
passed, 4 skipped, 35 subtests passed -- only the pre-existing unrelated
`test_go_live_wizard.py` failure. All 5 generated definitions validated
clean (`result: OK`, zero diagnostics) via
`aws stepfunctions validate-state-machine-definition` against real AWS,
confirming `ErrorPath`/`CausePath` (used in `SecFetchTaskFailed` to
surface the original caught error dynamically) is genuinely accepted ASL
syntax, not just something that looks plausible. Not yet deployed to prod
or live-verified -- pending explicit confirmation per this workstream's
live-action convention.

## Deployed + live-verified (2026-08-04)

Rebuilt+deployed warehouse/MDM images from `main`@`0abfa98d`, all 5 machines
confirmed live with the new states, ASL-validated clean. A real
`targeted-resync` run hit an unrelated failure (ticket 88) inside
`RunWarehouseTask`, exercising the new `Catch` for real: confirmed via
direct canonical-S3 read (`SELECT ... FROM pipeline_run_lease`) that
`sec_fetch_active` released cleanly (`status='idle'`, `run_id` matching
the execution) with zero manual intervention -- the exact failure mode
that required two manual recoveries during ticket 84's own verification
now self-heals.
