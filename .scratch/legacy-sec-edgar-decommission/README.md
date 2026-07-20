# Legacy `sec-edgar` stack decommission — 2026-07-19

## What this was

An orphaned April 2026 prototype ingest stack in account `690839588395`,
predating the `edgartools-*` platform naming, with **zero references in this
repository**. Discovered during a cleanup-and-audit pass. Its EventBridge
schedule was still ENABLED and firing nightly at 02:00, and every execution
FAILED (verified Jul 17/18/19) because the `sec-edgar-ingest` ECR repository
it launched no longer exists. The bucket keys even contain an unresolved
`<aws.events.event.time>` placeholder — the pipeline was broken from early on
(last successful S3 write 2026-04-14).

## Deleted (2026-07-19, definitions backed up in this directory)

| Resource | Name |
|----------|------|
| EventBridge schedule | `sec-edgar-daily-ingest` (was ENABLED, nightly 02:00) |
| Step Functions state machine | `sec-edgar-bronze-ingest` |
| ECS cluster | `sec-edgar-cluster` (0 services, 0 tasks) |
| ECS task definitions | `sec-edgar-ingest-01..04:3` (deregistered) |
| CloudWatch log groups | `/ecs/sec-edgar-ingest-01..04` |
| IAM roles | `sec-edgar-ecs-execution-role`, `sec-edgar-ecs-task-role`, `sec-edgar-scheduler-role`, `sec-edgar-stepfunctions-role` (inline `sec-edgar-inline-policy` removed from each) |

The `sec-edgar-ingest` ECR repository was already gone before this pass
(root cause of the nightly failures).

## Deliberately NOT deleted

- **S3 bucket `paulananth11-sec-edgar-bronze`** — 17 objects, ~97.6 MB, last
  write 2026-04-14. Data deletion is irreversible, so it is held for an
  explicit operator decision. It is the only non-`edgartools-*` bucket left
  in the account.

## Backups in this directory

Every deleted resource's full definition was captured before deletion:
`schedule-*.json`, `sfn-*.json`, `taskdef-*.json` (×4), `iam-*.json`
(role + inline policy + attached-policy list per role). The stack can be
recreated from these if ever needed.

## Post-deletion verification

- `iam list-roles` filtered on `sec-edgar`: empty.
- ECS clusters remaining: `edgartools-dev-warehouse`, `edgartools-prod-warehouse` only.
- No Step Functions state machine or EventBridge schedule matching `sec-edgar` remains.
