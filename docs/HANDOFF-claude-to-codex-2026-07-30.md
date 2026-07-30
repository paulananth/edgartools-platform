# Handoff: Claude → Codex — release-readiness ticket 49 schedule-wiring slice — 2026-07-30

**From:** Claude session on `claude/daily-identity-refresh-go-live`
**Repo:** `edgartools-platform` · `origin/main` @ `c9a9ada` (PR #314 merged) · PR #316 open,
2 commits ahead of `main` on this branch.
**Ask:** no action required to unblock this specific slice — informational handoff so a future
Codex session has the current state of release-readiness ticket 49 without re-deriving it, plus
one explicit scope note on where this ticket's ownership sits relative to the ticket 45 decision
Codex originally authored.

## Ticket lineage (why this is a Claude/Codex relay, not new work)

[Decide whether/how to narrow daily_incremental's Stage0 and set its actual schedule](.scratch/release-readiness/issues/45-decide-narrow-daily-incremental-stage0-and-cadence.md)
(ticket 45) was originally claimed and resolved by Codex — merged into `main` via PR #305
(`codex/wayfinder-daily-incremental`, commits `4f02854`/`2820021`). That ticket decided the
cadence (`12:00 UTC`, Mon-Sat Daily Identity Refresh / Sunday Identity Backstop Sweep), the
shared-lease non-overlap disposition (`deferred`, `backstop_overdue` carry-forward, 18h
stale-execution alarm), the schedule-ownership split (passive Terraform → explicit
`deploy-aws-application.sh` control), and the two-phase activation boundary.

[Implement and Activate the Bounded Daily Identity Refresh Schedule](.scratch/release-readiness/issues/49-implement-bounded-daily-identity-refresh-schedule.md)
(ticket 49) is the implementation task ticket 45 spawned. Claude has been implementing it across
three sessions/branches, each landing a slice:

1. `claude/daily-identity-refresh` (merged via PR #314) — `compute-identity-refresh-window`,
   `pipeline_run_lease` DB primitives, the bounded default path.
2. `claude/daily-identity-refresh-go-live`, commit `390a5de` (open, PR #316) — wired the lease
   into the state machine's actual branching (`AcquireLease` → `ReadLeaseResult` →
   `LeaseAcquiredCheck` → `{RefreshMode | Deferred}` → ... → `ReleaseLease`).
3. Same branch, commit `607c9b9` (this session, also folded into PR #316) — closed the two gaps
   slice 2's own progress notes flagged as still open: persisted `backstop_overdue` consumption
   (a deferred backstop now genuinely prioritizes the next available trigger slot, verified
   across multiple consecutive deferrals, not just one defer-then-succeed cycle) and
   EventBridge/Terraform schedule ownership (deleted the disabled passive-Terraform file, added a
   least-privilege scheduler IAM role to access Terraform, added
   `--configure-daily-incremental-schedule enable|disable` to `deploy-aws-application.sh`).

**No live overlap found.** The local `codex/wayfinder-daily-incremental` worktree
(`/Users/aneenaananth/projects/edgartools-platform-wayfinder-daily-incremental`) is a stale ref
sitting at the pre-PR-#305-merge tip — its own two commits are already fully merged into `main`
and superseded by everything above. Checked all other active Codex worktrees
(`edgartools-platform-claude-merge` on `codex/wayfinder-direct-evidence-go`,
`edgartools-platform-dashboard-acceptance` on `codex/dashboard-acceptance-integration`) for
uncommitted state — both clean, neither touches `daily_incremental`/`pipeline_run_lease`/
`deploy-aws-application.sh`.

## Current state

| Item | State |
| --- | --- |
| PR #316 | Open against `main`, title "feat(daily-incremental): wire identity-refresh lease + backstop_overdue schedule (ticket 49)", 2 commits, 865 unit+architecture tests passing, both Terraform roots (`infra/terraform/accounts/prod`, `infra/terraform/access/aws/accounts/prod`) `terraform validate` clean. Not yet merged — awaiting the repo owner's review/merge decision. |
| Ticket 49 | `Status: claimed` (not `resolved`) — see its "## Progress" sections (three, one per slice above) for full detail. |
| Prod | No prod deploy from this branch. `--configure-daily-incremental-schedule enable` has never been run against `690839588395`. |

## What is genuinely still open on ticket 49 (not started by any session yet)

1. **CloudWatch alerting** — ticket 45 requires alerting the AWS Operator on every `deferred`
   disposition, plus a separate alarm for an execution still active after 18 hours. No alarm/SNS
   resources exist yet for this.
2. **Phase 1 evidence-gathering** — ticket 49's two-phase activation boundary requires manual
   timing proof (Daily Identity Refresh ≤6h, Identity Backstop Sweep ≤18h), a forced
   late-daily-index-republish coverage fixture, and a concurrent-trigger deferral proof, all
   against one immutable Release Candidate, before Phase 2 can even be requested.
3. **Phase 2 Operator GO** — an explicit AWS Operator enable/hold decision, recorded on the
   ticket, plus live EventBridge state verification afterward.
4. **One precautionary check, not a blocker:** before the next `terraform apply` in
   `infra/terraform/accounts/prod`, run `terraform state list | grep daily_incremental` against
   the live `edgartools-prod-tfstate` backend to confirm the deleted file's resources were in fact
   never created (this session confirmed the enabling variable defaulted `false` with no tfvars
   override, and cross-checked the local `infra/.aws-tfstate-backups/` snapshots for zero
   `daily_incremental_scheduler` references — both corroborate "never created," but neither is a
   live state read).

## What Codex should actually do

Nothing is blocked on Codex right now. If a future Codex session picks up ticket 49's next slice
(most likely #1, CloudWatch alerting, since it's the smallest remaining implementation slice and
doesn't require a live prod window the way Phase 1 evidence-gathering does):

- Read ticket 49's three "## Progress" sections in full before starting — they're detailed and
  avoid re-deriving already-settled design decisions (e.g. why `stale_after_seconds` is 20h not
  18h, why `ReadLeaseResult` deliberately has no `Catch`, why the EventBridge cron uses `?` on
  day-of-month).
- Branch off PR #316's head (`607c9b9`) if it's still unmerged when that session starts, not off
  `main` directly — `deploy-aws-application.sh` and `pipeline_run_lease`'s schema are both touched
  by this PR and alerting work would likely touch both again.
- Per this session's new CLAUDE.md convention: run `/gof-refactor-reviewer` before starting, and a
  two-axis `/code-review` before calling the slice done.
