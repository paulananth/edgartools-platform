Type: task
Status: in_progress

## Question

`daily-incremental` has live CloudWatch alarm coverage for **timeouts only** — an
application-level pipeline failure (fail-closed `States.TaskFailed`, e.g. an ECS
task exiting non-zero) currently reaches no one. Close this gap so any
`daily-incremental` failure — timeout or application-level — reaches the confirmed
operator alert subscriber.

## Evidence (confirmed live this session, 2026-08-03, via AWS CLI — not from docs)

- `edgartools-prod-daily-incremental-timeout` — real, live CloudWatch alarm,
  `AWS/States` `ExecutionsTimedOut` metric, dimensioned to
  `arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-daily-incremental`,
  alarm action -> `arn:aws:sns:us-east-1:690839588395:sec-edgar-pipeline-alerts`.
  Created via `deploy-aws-application.sh --configure-daily-incremental-alarms enable`
  (guarded by `require_confirmed_operator_alert_topic`, tested in
  `tests/architecture/test_daily_incremental_alarm_controls.py`).
- That SNS topic has a **real, confirmed** email subscription
  (`thepaulananth@gmail.com`) — a genuine timeout would actually deliver.
- Reproduced the actual gap: `daily-incremental-ticket70-verify-1785720814`
  (2026-08-02T21:33 -> 2026-08-03T06:08) failed via `States.TaskFailed` — ECS
  task exit code 2, application error
  (`"recurring artifact pipeline had 0 failed candidates and 2 terminal repair
  candidates"`, see
  [ticket 74](74-daily-incremental-permanent-terminal-repair-block.md)) — **not**
  a timeout. `ExecutionsTimedOut` never incremented; no alert fired; the failure
  was only caught because someone was watching manually.
- Checked for an `ExecutionsFailed` alarm on the correct state machine — none
  exists. There IS a `sec-edgar-pipeline-failure` alarm on `ExecutionsFailed`,
  but its `StateMachineArn` dimension points at
  `arn:aws:states:us-east-1:690839588395:stateMachine:sec-edgar-bronze-ingest`,
  which **does not exist**
  (`describe-state-machine` -> `StateMachineDoesNotExist`, confirmed live). It's
  an orphaned alarm from an old naming convention, permanently `OK` from zero
  datapoints ("1 missing datapoint treated as NonBreaching"), not from real
  health — it provides no actual coverage.
- There is also a broader `infra/terraform/modules/pipeline_notifications/main.tf`
  module (EventBridge rule catching `FAILED` executions across all
  `edgartools-{env}-*` state machines -> SNS) — but it's gated behind
  `pipeline_notifications_enabled = false` (the default) in
  `infra/terraform/accounts/prod/terraform.tfvars`, and confirmed **not deployed**
  live (`aws events list-rules` shows no matching rule; no
  `edgartools-prod-pipeline-failures` SNS topic exists).
- Separately (context, not in scope here): confirmed via `aws events list-rules`
  that no EventBridge schedule currently triggers `daily-incremental`
  automatically at all — both runs inspected this session were started manually.
  That's [ticket 49](49-implement-bounded-daily-identity-refresh-schedule.md)'s
  territory (its own Progress notes already flag "CloudWatch alerting" as
  explicitly not done), not this ticket's.

## Scope

Close the failure-alarm gap for `edgartools-prod-daily-incremental` specifically.
Two independent moves, not mutually exclusive:

1. Add a real `ExecutionsFailed` CloudWatch alarm dimensioned to
   `arn:aws:states:us-east-1:690839588395:stateMachine:edgartools-prod-daily-incremental`,
   alarm action -> the same confirmed `sec-edgar-pipeline-alerts` topic —
   mirroring the existing `edgartools-prod-daily-incremental-timeout` pattern
   (same `deploy-aws-application.sh` off-by-default-flag convention,
   `require_confirmed_operator_alert_topic` guard, contract-tested the same way
   as `test_daily_incremental_alarm_controls.py`).
2. Retire (or repoint) the orphaned `sec-edgar-pipeline-failure` alarm — it
   references a state machine that no longer exists and provides zero real
   signal today; leaving it in place is misleading (looks like coverage, isn't).

Does **not** require re-litigating whether to enable the broader
`pipeline_notifications` Terraform module (catch-all across every
`edgartools-{env}-*` state machine) — that's a separate, larger-blast-radius
decision (affects `load_history`, `gold-refresh`, etc., not just
`daily-incremental`) worth its own ticket if the operator wants it; note the
option exists but don't fold it into this fix silently.

Does **not** cover adding a schedule for `daily-incremental` itself — that's
ticket 49's territory.

## Done when

- A live `ExecutionsFailed` alarm exists on the correct
  `edgartools-prod-daily-incremental` state machine ARN, wired to
  `sec-edgar-pipeline-alerts`, contract-tested the same way as the existing
  timeout alarm.
- The orphaned `sec-edgar-pipeline-failure` alarm is either deleted or
  repointed at a real, existing state machine — operator's call, recorded here.
- Confirmed live (not just planned) via `aws cloudwatch describe-alarms`.

## Progress (2026-08-03) — code + tests done, live deploy not yet run

Implemented move 1 (new `ExecutionsFailed` alarm): `configure_daily_incremental_alarms`
in `infra/scripts/deploy-aws-application.sh` now creates/deletes a second alarm,
`${NAME_PREFIX}-daily-incremental-failed` (`AWS/States` `ExecutionsFailed` metric, same
`StateMachineArn` dimension, same `sec-edgar-pipeline-alerts` topic, same
`require_confirmed_operator_alert_topic` guard, same off-by-default
`--configure-daily-incremental-alarms enable|disable` flag) -- mirrors the existing
timeout alarm exactly, one call handles both now. `disable` deletes both alarms in one
`cloudwatch delete-alarms` call.

Extended `tests/architecture/test_daily_incremental_alarm_controls.py`:
`test_enable_creates_the_execution_failure_alarm` (new) and
`test_disable_deletes_both_alarms` (renamed/extended from the timeout-only version) --
confirmed to fail against pre-fix code (3 of 5 tests fail: no `-failed` alarm created,
disable only deletes one alarm). `test_enable_creates_the_timeout_alarm` was extended to
assert both alarm names appear across the enable calls. Full
`tests/unit`+`tests/application`+`tests/architecture` suite: 1274 passed, 4 skipped, same
pre-existing unrelated `test_go_live_wizard.py` failure noted on tickets 75/76.

**Not yet done (both require a live prod AWS action, deliberately deferred for explicit
confirmation per this repo's destructive/shared-system-change convention):**
- Running `deploy-aws-application.sh --env prod --configure-daily-incremental-alarms
  enable --operator-alert-topic-arn arn:aws:sns:us-east-1:690839588395:sec-edgar-pipeline-alerts`
  to actually create the new `edgartools-prod-daily-incremental-failed` alarm live (the
  existing timeout alarm will be re-put with identical parameters -- idempotent, no-op
  in effect).
- Move 2 (orphaned `sec-edgar-pipeline-failure` alarm): recommend **delete**, not
  repoint -- it references a state machine (`sec-edgar-bronze-ingest`) that no longer
  exists at all, and repointing it at `edgartools-prod-daily-incremental` would just
  duplicate the new `-failed` alarm's `ExecutionsFailed` coverage under a stale name.
  Not yet executed -- a live `aws cloudwatch delete-alarms` against prod, same
  confirm-before-executing convention as the new alarm's deploy.
