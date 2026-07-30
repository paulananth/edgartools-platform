# 45 — Decide whether/how to narrow daily_incremental's Stage 0 and set its actual schedule

Type: grilling
Status: claimed
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
