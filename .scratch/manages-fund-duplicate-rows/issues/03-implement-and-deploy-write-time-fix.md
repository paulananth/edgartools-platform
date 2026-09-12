Type: task
Status: resolved
Blocked by: 02

**Repurposed by [Ticket 02](02-decide-write-time-fix-mechanism.md):** originally
scoped as "implement + deploy a write-time fix." Ticket 01 found the
write-time bug is a one-time historical event, already gone as a side
effect of the 2026-08-21 CRD-batching refactor (`869003da`) — 3+ weeks of
clean writes since. No code fix is needed. This ticket is now a
lightweight live-monitoring check instead.

## What to build

A periodic check (mirroring this repo's existing `mdm check-fence`
precedent — verifying a fixed assumption stays true, not re-deriving it
from scratch each time) that alerts if any MANAGES_FUND `relationship_id`
ever gets a second currently-active, non-quarantined, non-superseded row
with byte-identical `properties`/`valid_from_date`/`valid_to_date` to an
existing one. Cheap insurance against Ticket 01's unconfirmed-mechanism
gap — if this reasoning turns out wrong, this catches a regression
quickly instead of silently letting a new backlog regrow.

## Acceptance

- [x] Check queries MDM Postgres for new post-cleanup-baseline duplicate
      groups (scoped to MANAGES_FUND only — this is not a general
      relationship-integrity monitor).
- [x] Wired into whatever this repo's existing alerting mechanism is
      (check `mdm check-fence`'s own wiring for precedent) rather than a
      standalone script nobody runs.
- [x] `/gof-refactor-reviewer` consulted before editing (repo hard rule).
- [x] `/code-review` (Standards, Spec, GoF) run before PR is ready.

## Answer

Implemented as a new stateless module,
`edgar_warehouse/mdm/manages_fund_duplicate_monitor.py`
(`check_manages_fund_duplicates(engine)` → `DuplicateCheckResult`), wired
into a new `mdm check-manages-fund-duplicates` CLI subcommand
(`edgar_warehouse/mdm/cli.py`) and the consolidated `mdm_utility` Step
Functions machine's mode list, deploy-script schedule
(`rate(1 day)`, off by default) and CloudWatch alarm
(`infra/scripts/deploy-aws-application.sh`) — the exact same shape as the
existing `mdm check-fence` precedent this ticket named.

The known-backlog/new-regression distinction (the ticket's own stated
purpose) is a fixed constant, `KNOWN_BACKLOG_CUTOFF = 2026-08-22` (one day
after the `869003da` CRD-batching refactor that ended the historical
write-time bug) — a duplicate active-row group only flags if its newest
row's `created_at` postdates that cutoff. Chosen over a persisted baseline
snapshot: every known-backlog row is provably from 2026-08-19 (Ticket 01's
finding), so a fixed constant cleanly separates "the known one-time
backlog" from "a genuine new regression" with zero new state/infrastructure.

`/gof-refactor-reviewer` was consulted before writing any code (this
session, prior turn): verdict was that direct mirroring of the
`check-fence` pattern was sound at this scale (second instance of the
shape), with no shared abstraction justified yet for the CLI-handler
plumbing. The one place cumulative evidence *did* justify a small
generalization — `put_fence_monitor_metric_and_alarm` →
`put_mdm_check_metric_and_alarm`, parameterized on `event_name`/
`period_seconds` since the old version hardcoded both — was made in this
same diff, with the existing fence-monitor call site updated to pass its
prior values explicitly (behavior-preserving).

The mandatory 3-axis `/code-review` (run against the real diff, not just
the pre-code consult, per this repo's own documented lesson that a
pre-code consult can miss a diff-level detail) found zero blocking
findings on any axis: Standards (0 hard violations; 2 non-blocking
judgement-call notes on smells inherited unchanged from `check-fence`'s
own existing shape), Spec (0 missing/wrong requirements; the cutoff logic
specifically verified correct and tested; 1 non-blocking scope note on the
alarm-helper generalization, judged low-risk), GoF (0 findings — the GoF
reviewer independently re-verified, against the actual diff, that the
pre-code consult's judgment held: direct mirroring was correct, and the
one generalization made was the right, cheap call).

Tests: `tests/architecture/test_mdm_utility_state_machine.py` (extended
for the new mode, 9/9 passing); `tests/integration/
test_manages_fund_duplicate_monitor_postgres.py` (5 tests against a real
ephemeral Postgres container, including direct proof of both halves of
the cutoff split); `tests/mdm/test_check_manages_fund_duplicates_cli.py`
(2 CLI-handler unit tests). Full `tests/mdm/` + `tests/architecture/`
sweep: 1372 passed, 3 skipped. Full repo suite: 3440 passed, 8
pre-existing/unrelated Postgres-integration failures (documented
elsewhere in `CLAUDE.md`), 12 skipped. mypy clean on the new module.

Ticket 04 (`decide-and-run-backlog-cleanup`) remains open, blocked only by
the already-resolved Ticket 01 — unaffected by this ticket's scope.
