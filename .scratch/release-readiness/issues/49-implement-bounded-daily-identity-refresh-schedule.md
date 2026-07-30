# Implement and Activate the Bounded Daily Identity Refresh Schedule

Type: task
Status: open
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

## Done when

Focused tests, repository CI, deployed definitions, manual production timing,
coverage evidence, and the concurrency-deferral proof all pass for one
immutable Release Candidate. The ticket records the AWS Operator's explicit
enable/hold decision and verifies live EventBridge state afterward.
