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

## Progress (2026-07-30, later same day — go-live branch, lease wired in)

On branch `claude/daily-identity-refresh-go-live` (based on `main`, which now
carries the merged Refresh-behavior work above): implemented the
"AcquireLease/ReleaseLease not yet inserted into the state machine" gap from
the previous session's list.

**Done, tested (854 unit+architecture tests passing), gof-refactor-reviewer
and two-axis `/code-review` run against the diff, findings applied:**
- State machine restructured: `RefreshModeCheck`/`RefreshModeDefault` now
  route to a new `AcquireLease` step (ECS task calling
  `acquire-identity-refresh-lease --mode <refresh_mode>`) before either
  refresh mode is chosen. Since `ecs:runTask.sync` can't surface app-level
  stdout to a Choice state, `AcquireLease` writes `lease_result.json` to S3
  as its source of truth (new `identity_refresh_lease_path()` template);
  `ReadLeaseResult` reads it back via `aws-sdk:s3:getObject` +
  `States.StringToJson`; `LeaseAcquiredCheck` is fail-closed (only an
  explicit `lease_acquired=true` proceeds to `RefreshMode`, everything else
  falls through `Default` to a `Deferred` terminal state). `GoldRefresh` now
  routes to `ReleaseLease` (best-effort — a `Catch` routes release failures
  to a non-fatal terminal state) instead of ending directly. `bootstrap`'s
  definition confirmed unaffected.
- `acquire_pipeline_run_lease` (`silver_store.py`) gained a staleness-based
  reclaim: a lease held past `stale_after_seconds` (default **20h** — 2h of
  margin past the Identity Backstop Sweep's own 18h completion/alarm bound,
  not 18h itself, to avoid a new run's acquire racing a legitimately-still-
  finishing backstop mid-`ReleaseLease`) is reclaimable by a later acquirer.
  This is the actual safety net for a crashed run; release-on-failure
  elsewhere is deliberately best-effort, not wrapped in Catch on every
  downstream state (a "wrap everything in Parallel+Catch" alternative was
  considered and rejected as disproportionate ASL surgery — advisor's call).
- Extracted `IDENTITY_REFRESH_LEASE_NAME` (`warehouse_orchestrator.py`) as a
  single source of truth for the lease's name, and a test
  (`test_read_lease_result_key_matches_the_real_path_resolver`) cross-checking
  the deploy script's hand-typed S3 key against the real path-resolver output
  — both fix the same class of gap Standards-axis review found: the lease
  *name* and the lease-result *path* were each duplicated across files with
  nothing tying the copies together, so an edit to one copy could silently
  break the mechanism.
- `Deferred`'s own execution output now carries a labeled
  `{"disposition": "deferred", "lease_check": {...}}` field (via `Parameters`/
  `ResultPath`) instead of relying entirely on `$` passthrough — Spec-axis
  review found the prior bare Pass state's disposition was only visible one
  layer down (CloudWatch events), not in the execution's own output where an
  operator would look first.
- Clarified (deploy-script comment + test docstring + a new
  `test_read_lease_result_has_no_catch`) that `ReadLeaseResult` deliberately
  has no `Retry`/`Catch`: a missing/corrupt `lease_result.json` fails the
  execution outright rather than falling through to `Deferred` — Spec-axis
  review found the original comments overclaimed that "anything else (false,
  missing, malformed)" reaches `Deferred`, when only a successfully-parsed
  `lease_acquired: false` actually does. This is the correct behavior (an
  unknown failure mode must not be silently relabeled as the benign "lease
  busy" case), so the fix was to the documentation, not the code.

**Still explicitly NOT done (unchanged from the list above, plus two new
gaps this session's own review surfaced and left open rather than
building further):**
- EventBridge/Terraform schedule changes, CloudWatch alerting (deferral
  alerts, 18h stale-execution alarm) — still entirely unstarted; these were
  the two options *not* chosen when this session picked "wire the lease into
  the state machine" over "EventBridge/Terraform schedule wiring" as the
  branch's scope.
- **`backstop_overdue` is recorded but never consumed.** `lease_result.json`
  and the `identity_refresh_lease_deferred` event both carry this flag when
  a losing acquirer was the backstop mode, but nothing reads it to force the
  *next* available slot into backstop mode ahead of a narrow daily refresh
  (ticket 45's "prioritize it at the next available slot" requirement) —
  that logic doesn't exist yet because the thing that would consume it (the
  schedule/slot-selection mechanism) is itself one of the still-unstarted
  EventBridge items above.
- No prod deploy of this branch — code, tests, and commits only.

**Status remains `claimed`.**

## Done when

Focused tests, repository CI, deployed definitions, manual production timing,
coverage evidence, and the concurrency-deferral proof all pass for one
immutable Release Candidate. The ticket records the AWS Operator's explicit
enable/hold decision and verifies live EventBridge state afterward.
