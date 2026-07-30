# 45 — Decide whether/how to narrow daily_incremental's Stage 0 and set its actual schedule

Type: grilling
Status: resolved
Blocked by: (none)

## Question

Ticket 43 (Investigate why daily_incremental reprocesses the full active universe) found that
narrowing `Stage0CompanyIdentity` from the full ~26,300-CIK tracked universe down to a given
day's `impacted_ciks` (per SEC's daily-index) is architecturally possible, reuses only
already-built/already-tested code (the unscheduled `catch-up-daily-form-index` command's
index-only parse, plus `bootstrap-fundamentals --mode company-identity`'s already-implemented
but unused `--cik-list` path), and would cut Stage 0's per-run workload by roughly an
order of magnitude (2,925 of ~26,300 CIKs filed anything on the one sample day checked,
2026-07-28) — but is a genuine operator trade-off, not a pure bug fix, because it would
introduce two specific, currently-unmitigated coverage gaps:

1. Per-CIK `submissions.json` drift (name/address changes) with no accompanying same-day
   filing — invisible to a daily-index-scoped `impacted_ciks` list.
2. SEC daily-index republish after this repo's checkpoint already marked that date
   `succeeded` (live-evidenced: `company.20260710.idx` republished ~37h after its normal
   publish window) — combined with the existing no-`--force` cache short-circuit, a CIK whose
   only activity appears in a late correction is silently missed on every subsequent run.

Separately, ticket 43 also found `daily_incremental` has **no EventBridge schedule at all** —
its only execution to date was a manual, ad-hoc `start-execution`. "Daily" is aspirational in
the state-machine's name only; nobody has decided the actual cadence yet, which makes "does a
~10-11 hour run overlap with the next scheduled trigger" unanswerable until a cadence exists.

Decide:
1. Narrow Stage 0 now (accepting/documenting the two gaps as known limitations), narrow it with
   an added mitigation (e.g. a periodic full-universe sweep as a backstop, or an explicit
   `--force` re-check of the most recent N days on every run to catch late republishes), or leave
   Stage 0 full-universe for now and revisit only if runtime becomes an operational problem?
2. If narrowing ships, what wires the new pre-stage in (a state-machine definition change to
   `deploy-aws-application.sh`, reusing `catch-up-daily-form-index`'s logic ahead of
   `Stage0CompanyIdentity`) — is this scoped as part of this ticket's resolution or its own
   follow-up implementation ticket?
3. What cadence should `daily_incremental` actually run on, and via what mechanism (EventBridge
   scheduled rule, matching the deploy script's existing patterns for other schedules)? This is
   a prerequisite for the overlap-risk question ticket 43 flagged as unanswerable without a
   schedule.

This is a HITL grilling ticket — the operator must weigh the runtime-savings vs. coverage-gap
trade-off directly; do not resolve it as a pure engineering judgment call.

## Answer

### Refresh coverage

Replace the daily full-universe company-identity stage with a bounded **Daily
Identity Refresh**:

- parse SEC daily indexes before company identity processing;
- force-recheck the trailing seven calendar days on every run;
- union the tracked `impacted_ciks` from those refreshed indexes;
- process that union through the existing explicit-CIK company-identity path;
  and
- refresh global ticker/exchange reference data once per run.

This does not accept either known coverage gap. The rolling forced recheck
backstops late SEC index republication. A weekly **Identity Backstop Sweep**
processes the full tracked universe to cover administrative `submissions.json`
changes without a filing signal.

The decision is based on current direct evidence: the first production
`daily_incremental` execution remained `RUNNING` during this grilling;
`Stage0CompanyIdentity` alone took 10h16m, from 2026-07-29 10:52 ET to 21:08
ET, before `RunWarehouseTask` began. No live EventBridge schedule targeted the
state machine. Leaving that full-universe stage on a daily cadence would create
unbounded overlap risk without improving the two gaps in a controlled way.

### Cadence

Use one **Identity Refresh Slot** at `12:00 UTC` each day:

- Monday through Saturday: Daily Identity Refresh.
- Sunday: Identity Backstop Sweep instead of the narrow refresh.

`12:00 UTC` is 7 AM EST / 8 AM EDT, after the platform's conservative 6 AM ET
daily-index availability boundary. The weekly backstop's 18-hour maximum leaves
six hours before Monday's slot.

### Schedule ownership

Recurring triggers belong to the explicit AWS application rollout boundary,
not passive Terraform:

- remove the disabled EventBridge rule/target resources and enablement variable
  currently present in `infra/terraform/accounts/prod`;
- retain only least-privilege scheduler identity/access in AWS access
  Terraform; and
- add explicit, off-by-default schedule configure/disable controls to
  `deploy-aws-application.sh`, run as `sec_platform_deployer`.

Ordinary application deployment must not enable recurrence. This corrects the
existing repository contradiction: current passive Terraform contains a gated
schedule even though the repository's AWS model forbids schedules there.

### Non-overlap disposition

Both refresh modes share one atomic lease. A scheduled slot that cannot acquire
the lease:

- starts no duplicate data work;
- records `deferred` and alerts the AWS Operator;
- relies on the next successful daily refresh to catch up filing-signaled work;
  and
- if it was the weekly backstop, records `backstop_overdue` so the next free
  slot runs the backstop before a narrow refresh.

An execution still active after 18 hours raises a separate stale-execution
alarm. A deferral is an explicit operational disposition, not a pipeline PASS
or an invisible skip.

### Activation boundary

Implementation and activation are separate phases. Deploy the implementation
with both schedules disabled. Before asking to enable them, bind evidence to one
immutable Release Candidate showing:

1. one manual Daily Identity Refresh completes the full downstream chain,
   including the forced seven-day recheck, in at most 6 hours;
2. one manual Identity Backstop Sweep completes the same downstream chain in at
   most 18 hours;
3. the daily run covers the exact expected impacted-CIK union, including a
   forced late-index-republish fixture;
4. the backstop covers the complete tracked universe; and
5. a deliberate competing trigger records `deferred` without starting duplicate
   data work.

The AWS Operator attests this evidence at a HITL checkpoint. Only an explicit
AWS Operator GO enables recurring schedules; tests, deployment, or timing PASS
cannot enable them automatically. Disabling a schedule remains an immediate
operator safety action.

Implementation, live proof, and the activation checkpoint belong to
[Implement and Activate the Bounded Daily Identity Refresh Schedule](49-implement-bounded-daily-identity-refresh-schedule.md).
