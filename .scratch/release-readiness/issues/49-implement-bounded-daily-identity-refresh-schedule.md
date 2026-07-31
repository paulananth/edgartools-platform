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
- Preserve an Identity Backstop Sweep that processes the complete active
  company-eligible universe: `entity_type = operating` or present in the
  captured canonical SEC `company_tickers` snapshot.

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
- the daily run covers the exact expected intersection of the forced
  impacted-CIK union and company-eligible universe, including a forced
  late-index-republish fixture;
- the backstop covers the complete company-eligible universe from the same
  captured reference snapshot;
- both identity modes record the reference snapshot identity, input/eligible/
  excluded counts, selected-CIK digest, and pre-stage elapsed time; strict Map
  success plus the execution timeline provides processed-CIK and end-to-end
  duration evidence; and
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

## Progress (2026-07-30, later same day — schedule wiring + backstop_overdue consumption)

Closed the two gaps the prior progress note above left open: `backstop_overdue`
consumption, and EventBridge/Terraform schedule wiring. Both landed together
on `claude/daily-identity-refresh-go-live` on top of the lease-wiring commit
(open as PR #316).

**backstop_overdue is now real, persisted state, not just a per-run flag.**
Consulted advisor before writing code: two static cron rules (Mon-Sat →
`daily`, Sun → `backstop`) structurally cannot satisfy "prioritize the next
available slot" on their own — Monday's rule always sends `daily` regardless
of what Sunday did. Fixed by moving mode resolution *into* the pipeline:
- `pipeline_run_lease` gained a persisted `backstop_overdue` column
  (migration `008_pipeline_run_lease_backstop_overdue` — DuckDB rejects a
  `NOT NULL` constraint on `ALTER TABLE ADD COLUMN`, so the migration uses
  `DEFAULT FALSE` without it, matching this file's other `ADD COLUMN`
  migrations; the `CREATE TABLE` DDL for fresh stores keeps `NOT NULL`).
- `mark_pipeline_run_lease_backstop_overdue()` sets it when a `backstop`-mode
  acquire attempt is deferred; `release_pipeline_run_lease()` clears it via
  `CASE WHEN mode = 'backstop' THEN FALSE ELSE backstop_overdue END` — a
  `daily`-mode release passing through must never accidentally clear an
  overdue backstop it had nothing to do with.
- `acquire-identity-refresh-lease` now resolves an `effective_mode` from the
  persisted flag *before* acquiring (overriding the trigger's own
  `--mode`/`requested_mode`), and writes the resolved value — not the raw
  request — into `lease_result.json`.
- A new `ApplyEffectiveRefreshMode` ASL Pass state overwrites `$.refresh_mode`
  from `$.lease_check.parsed.mode` right after `LeaseAcquiredCheck`'s
  fail-closed true branch, so the existing `RefreshMode` dispatch (which
  chooses `ComputeWindows` vs `ComputeIdentityRefreshWindow`) reflects the
  lease's decision, not the trigger payload — reusing the same "Pass state
  overwrites a top-level field" idiom `RefreshModeDefault` already used.
- Verified the mechanism survives more than one missed slot, not just a
  single defer-then-succeed cycle (a genuine gap the Spec-axis code-review
  caught in the first version of this coverage): a new test drives Sunday's
  backstop deferred → Monday's backstop-resolved retry *also* deferred →
  Tuesday's trigger still resolves to `backstop` → only Tuesday's successful
  `backstop`-mode release finally clears the flag.

**EventBridge schedule moved from passive Terraform to an explicit,
off-by-default deploy-script control**, per ticket 45's exact requirement:
- Deleted `infra/terraform/accounts/prod/scheduled_daily_incremental.tf`
  (and its `daily_incremental_schedule_enabled` variable) — confirmed safe
  first: the variable defaulted to `false`, no tfvars anywhere set it `true`,
  and `terraform validate` is clean with the file gone, so every resource in
  it was `count = 0` in prod and this is a pure no-op removal, not surgery
  on live state. (Standards-axis code-review caveat, not fully closable from
  this sandbox: this reasoning is corroborated by the local
  `infra/.aws-tfstate-backups/` snapshots, which contain zero references to
  `daily_incremental_scheduler`, but a live `terraform state list` against
  the real `edgartools-prod-tfstate` backend was not run — worth one before
  the next `accounts/prod` apply, purely as a sanity check.)
- Added `infra/terraform/access/aws/accounts/prod/scheduled_daily_incremental.tf`
  (new file, same name as the deleted one, different root): only a
  least-privilege `daily_incremental_scheduler` IAM role +
  `states:StartExecution` policy scoped to exactly the
  `edgartools-prod-daily-incremental` state machine ARN. Created
  unconditionally (no enable flag) — the role alone starts nothing, since no
  rule/target is created in Terraform at all; new output
  `daily_incremental_scheduler_role_arn`.
- Added `--configure-daily-incremental-schedule enable|disable` and
  `--daily-incremental-scheduler-role-arn <arn>` to
  `infra/scripts/deploy-aws-application.sh`. This is a standalone action —
  it exits immediately after configuring, before any image build, task
  definition registration, or state-machine deploy runs, so it can never be
  an accidental side effect of an ordinary `--env prod` deploy. `enable`
  creates/updates two rules via `put_daily_incremental_schedule_rule()` (a
  gof-refactor-reviewer finding: the two rule blocks were near-identical,
  extracted into one shared helper) — `cron(0 12 ? * MON-SAT *)` sending
  `{"refresh_mode": "daily"}`, and `cron(0 12 ? * SUN *)` sending
  `{"refresh_mode": "backstop"}`, both against the deterministic
  `${NAME_PREFIX}-daily-incremental` state machine ARN and the scheduler
  role above. `disable` removes targets and deletes both rules, and is a
  clean no-op if they don't exist. Not yet run against prod — this PR adds
  the capability only.

**Process, per this session's CLAUDE.md convention:** ran
`/gof-refactor-reviewer` (one finding, fixed: the duplicated rule-setup
blocks above) and a full two-axis `/code-review` against the lease-wiring
commit (`390a5de`, i.e. scoped to just this session's diff, not re-reviewing
already-reviewed work). Findings applied:
- Standards axis: no hard violations. Fixed a real test-infrastructure
  fragility — `test_daily_incremental_schedule_controls.py`'s function-source
  extraction anchored on a guard string
  (`if ! is_empty "$CONFIGURE_DAILY_INCREMENTAL_SCHEDULE"; then`) that's
  duplicated in the deploy script (it also opens the CLI-argument validation
  block); a future reorder of the two occurrences relative to the function
  definitions could have silently truncated the extracted source. Fixed by
  anchoring on the more specific, provably-unique
  `<closing brace>, blank line, if-guard` sequence instead, while still
  excluding the guard's own body from what's actually sourced (the original
  fix attempt included the guard's call line in the extracted text, which
  broke all 6 tests with a dangling unterminated `if` — caught immediately
  by re-running the suite before considering this done).
- Spec axis: cadence (`12:00 UTC`, Mon-Sat / Sun) and cron syntax
  (`?`/day-of-week form) confirmed correct against ticket 45's literal text;
  no scope creep; CloudWatch alerting and Phase 1/2 correctly out of scope
  for a code diff. One real gap found and fixed: the original tests only
  proved a single defer-then-succeed cycle for `backstop_overdue`, not that
  it survives multiple consecutive deferrals — added the two-consecutive-
  deferrals test described above.

Full test suite: 865 passed (unit + architecture), 4 skipped. Both Terraform
roots (`accounts/prod`, `access/aws/accounts/prod`) `terraform validate`
clean.

## Progress (2026-07-31 — company-only identity universe)

The scheduled identity scope now uses one reusable silver eligibility query:
active tracked CIKs whose `sec_company.entity_type` is `operating` or whose
CIK is present in the captured canonical `company_tickers` snapshot. Daily
mode intersects the forced seven-day impacted-CIK union with that eligibility
set. Backstop mode emits the complete eligible set through the same explicit
`cik_list` batch Map; the old scheduled `ComputeWindows`/
`Stage0CompanyIdentity` all-entity branch has been removed without changing
the independent load-history or explicit-CIK repair paths.

The pre-stage records the canonical ticker snapshot path and SHA-256, input,
active-tracked, eligible, excluded, and selected counts, a stable exact
selected-CIK digest, mode, and pre-stage duration. Empty eligibility fails
closed to an empty scheduled batch rather than falling back to all impacted
filers.

Phase 1 evidence must now prove exact company-eligible-universe parity for
both modes using those emitted identities and counts. It must not compare the
backstop against the approximately 26,300-CIK all-entity tracked universe.
The selected digest becomes processed evidence only when the strict
`Stage0CompanyIdentityBounded` Map succeeds; its Step Functions execution
timestamps, not the pre-stage timer, establish identity-stage and full-chain
elapsed time.

**Still not done:** CloudWatch alerting (deferral alerts, 18h/20h-stale
execution alarm), actually running `--configure-daily-incremental-schedule
enable` against prod, Phase 1 manual evidence-gathering, Phase 2 Operator
GO checkpoint. **Status remains `claimed`.**

## Done when

Focused tests, repository CI, deployed definitions, manual production timing,
coverage evidence, and the concurrency-deferral proof all pass for one
immutable Release Candidate. The ticket records the AWS Operator's explicit
enable/hold decision and verifies live EventBridge state afterward.

## Progress (2026-07-31 — alerting implemented; production rollout blocked by authority and delivery)

Completed the remaining alerting implementation on the combined release-candidate
base `47005767bc9efcc677e346ab06ca53c9bb00ad0b`:

- the Daily Identity Refresh state machine has a hard top-level
  `TimeoutSeconds=64800` bound, so an execution still active at 18 hours ends
  as `TIMED_OUT` rather than continuing silently;
- every explicit lease-busy disposition routes through a retrying direct SNS
  publish before the terminal `deferred` output, avoiding the false claim that
  a CloudWatch alarm state transition can notify once for every metric event;
- an off-by-default standalone deploy control creates or removes the distinct
  `AWS/States ExecutionsTimedOut` CloudWatch alarm, requires an in-account SNS
  topic with at least one confirmed subscription, and never deploys workloads
  or enables recurrence;
- AWS access Terraform grants the Step Functions role `sns:Publish` only to
  `arn:aws:sns:us-east-1:690839588395:sec-edgar-pipeline-alerts` and exports
  that ARN for the operator deploy boundary.

Focused architecture tests pass, the full unit+architecture suite passes,
`bash -n` and production access Terraform validation pass, and the live AWS
`ValidateStateMachineDefinition` API returns `OK` with no diagnostics for the
generated daily definition. The GoF review found no evidence-backed catalog
refactor worth adding to this composition-root script.

No production mutation was performed. The required profile resolves to the
correct account but the actual caller is
`arn:aws:iam::690839588395:user/admin-user`, not a verified
`sec_platform_deployer` principal. In addition, the live
`sec-edgar-pipeline-alerts` topic has zero confirmed subscriptions. The live
state machine remains revision `fc38774b-1da4-4e33-9d34-a0c43cd47e27`, with
zero daily schedule rules and zero CloudWatch alarms. Phase 1 manual daily,
backstop, late-republish, repair-routing, and competing-trigger evidence is
therefore still pending. Status remains `claimed`; schedules remain disabled.
