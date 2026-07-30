# Implement and Activate the Bounded Daily Identity Refresh Schedule

Type: task
Status: claimed
Blocked by: 45

## Question

How must the accepted Daily Identity Refresh, Identity Backstop Sweep, schedule
ownership, non-overlap policy, and two-phase activation boundary from
[Decide whether/how to narrow daily_incremental's Stage 0 and set its actual schedule](45-decide-narrow-daily-incremental-stage0-and-cadence.md)
be implemented and proven before recurring production triggers are enabled?

## Required work

### Refresh behavior

- Add an index-only pre-stage ahead of company identity processing.
- Force-recheck the trailing seven calendar days of SEC daily indexes and use
  the union of their tracked `impacted_ciks` for the Daily Identity Refresh.
- Invoke the existing explicit-CIK company-identity path in bounded chunks.
- Refresh global ticker/exchange reference data once per refresh rather than
  once per CIK window.
- Preserve an Identity Backstop Sweep that processes the complete tracked
  universe.

### Schedule ownership and cadence

- Remove EventBridge rules/targets and their enablement variable from passive
  AWS Terraform.
- Keep only least-privilege scheduler identity/access resources in AWS access
  Terraform.
- Add explicit, off-by-default operator controls to the AWS application deploy
  boundary for:
  - Daily Identity Refresh at `12:00 UTC`, Monday through Saturday.
  - Identity Backstop Sweep at `12:00 UTC` Sunday.
- Run schedule configuration as `sec_platform_deployer`; never enable recurrence
  as a side effect of ordinary application deployment.

### Non-overlap and observability

- Use one atomic lease shared by both refresh modes.
- When the lease is busy, record the new Identity Refresh Slot as `deferred`
  without starting duplicate data work.
- Carry a deferred backstop as `backstop_overdue` and prioritize it at the next
  available slot before a narrow refresh.
- Alert the AWS Operator on every deferral and separately when an execution
  remains active for 18 hours.
- Preserve secret-safe status and evidence for slot disposition, lease
  acquisition/release, active execution identity, and alert delivery.

### Two-phase activation

Phase 1 implements and deploys with both schedules disabled. Before the HITL
checkpoint, collect Release-Candidate-bound evidence that:

- one manual Daily Identity Refresh completes the full downstream chain with
  the forced seven-day recheck in at most 6 hours;
- one manual Identity Backstop Sweep completes the full downstream chain in at
  most 18 hours;
- the daily run covers the exact expected impacted-CIK union, including a
  forced late-index-republish fixture;
- the backstop covers the complete tracked universe; and
- a deliberate competing trigger records `deferred` without starting duplicate
  data work.

Phase 2 pauses for explicit AWS Operator review. Only an explicit AWS Operator
GO may enable the recurring schedules. Passing automation must never enable
them automatically. Disabling either schedule remains an immediate operator
safety action.

## Progress (2026-07-30, this session)

Implemented on branch `claude/daily-identity-refresh` (based on
`claude/gold-task-memory-bump`, so it carries gold-build-memory-reliability
ticket 03's fix too — needed since this ticket's own evidence gate runs
through the same `RunWarehouseTask`/gold-build path):

**Done, tested (843 unit+architecture tests passing):**
- `compute-identity-refresh-window` CLI command
  (`edgar_warehouse/application/warehouse_orchestrator.py`): force-rechecks
  the trailing N (default 7) calendar days via `_load_daily_index_for_date(...,
  force=True)` — unlike `daily-incremental`'s own already-succeeded-checkpoint
  short-circuit, this always re-fetches, so a late SEC daily-index republish
  within the window is still caught (the second accepted gap from ticket 45's
  Answer). Unions the impacted CIKs, refreshes ticker/exchange reference data
  once (not once per day), filters to the active tracked universe, and writes
  the union as batched `cik_list` JSONL reusing `seed-universe`'s existing
  batch-file shape/path (`reference/cik_universe/runs/{run_id}/cik_batches.jsonl`)
  — no new path-template plumbing needed.
- `pipeline_run_lease` table + `acquire_pipeline_run_lease`/
  `release_pipeline_run_lease`/`get_pipeline_run_lease` on `SilverDatabase`
  (`edgar_warehouse/silver_store.py`), plus `acquire-identity-refresh-lease`/
  `release-identity-refresh-lease` CLI commands. Atomic acquire via a
  conditional `ON CONFLICT ... DO UPDATE ... WHERE status != 'held'` upsert
  (verified against DuckDB directly, not assumed). On conflict, the acquire
  command records `lease_acquired=False` (and a `backstop_overdue` flag when
  the losing mode was `backstop`) via a structured event rather than raising —
  ticket 45's "deferred, not an invisible skip."
- `deploy-aws-application.sh`'s `daily_incremental` state-machine branch
  restructured: new `RefreshModeCheck`/`RefreshModeDefault`/`RefreshMode`
  Choice trio at `StartAt`. Default (no `refresh_mode` input, i.e. the Daily
  Identity Refresh) now routes through the new bounded
  `ComputeIdentityRefreshWindow` → `Stage0CompanyIdentityBounded` (a
  `--cik-list`-driven Map, same shape/`MaxConcurrency=1` as the existing
  Stage0 Map but reading the batched union instead of the full universe).
  `refresh_mode="backstop"` still routes through the **original, untouched**
  `ComputeWindows` → `Stage0CompanyIdentity` full-universe pair — the Identity
  Backstop Sweep. Both converge on `RunWarehouseTask`. `bootstrap`'s
  definition is confirmed unaffected (it never had this prefix).
  Verified via a new architecture test
  (`tests/architecture/test_daily_identity_refresh_state_machine.py`) that
  generates the real state-machine JSON, mirroring gold-build-memory-reliability
  ticket 02's proven pattern — plus 2 pre-existing
  `test_daily_incremental_state_machine.py` tests updated to match the new
  default path (the old full-universe default was the thing being replaced).

**Explicitly NOT done this session (per advisor guidance — see reasoning
below), left for follow-up:**
- The lease is **not wired into the state machine's branching**. `ecs:runTask.sync`
  doesn't surface app-level stdout/metrics (like `lease_acquired`) to a Choice
  state directly — resolving that (e.g. the acquire command exiting non-zero
  on conflict so a `Catch` can route to a `Deferred` terminal state, vs. some
  other signal-passing mechanism) is real design work, not mechanical wiring,
  and is left open rather than guessed at under this session's scope.
- `AcquireLease`/`ReleaseLease` states are not yet inserted into the state
  machine at all (the CLI commands and DB layer exist and are tested in
  isolation, but nothing calls them from the SFN definition yet).
- EventBridge schedule changes (removing the disabled rule from passive
  Terraform, adding off-by-default `deploy-aws-application.sh` controls) —
  entirely deferred; this ticket has not touched Terraform.
- CloudWatch alerting (deferral alerts, 18h stale-execution alarm) — not
  started.
- The full Phase 1 evidence-gathering (≤6h Daily Identity Refresh timing,
  ≤18h backstop timing, forced late-republish coverage fixture, concurrent-
  trigger deferral proof) and the Phase 2 AWS Operator activation checkpoint —
  neither is achievable in a single session regardless of implementation
  speed (the backstop timing bound alone is 18 hours), and no prod deploy of
  this branch has been done — code + tests + commit only, per this ticket's
  own two-phase design and advisor's explicit "don't deploy this session"
  guidance (a prod deploy right now would also confound gold-build-memory-
  reliability ticket 03's own in-flight verification, which this branch's
  base carries).

**Status kept at `claimed`, not `resolved`** — the "Refresh behavior" engineering
work is done and tested, but the lease/schedule/observability wiring and the
full evidence-gathering + Operator GO remain. Whoever picks this up next
should start from the "Explicitly NOT done" list above.

## Done when

Focused tests, repository CI, deployed definitions, manual production timing,
coverage evidence, and the concurrency-deferral proof all pass for one
immutable Release Candidate. The ticket records the AWS Operator's explicit
enable/hold decision and verifies live EventBridge state afterward.
