# Post-Handoff ECS and Step Functions Baseline — 2026-08-09

## Evidence identity

- Operator confirmed the Claude handoff complete on 2026-08-09.
- Repository baseline: `main` / `origin/main` commit `96daa74e`.
- AWS caller account: `690839588395`.
- Region: `us-east-1`.
- ECS cluster: `edgartools-prod-warehouse`.
- Evidence source: live read-only STS, ECS, ECR, and Step Functions APIs.

This artifact records inventory, not authorization to stop tasks, deregister
revisions, update workflows, or delete resources.

## Cluster state

- Cluster status: `ACTIVE`.
- Container Insights: enabled.
- ECS services: zero.
- Running tasks: zero.
- Pending tasks: zero.
- Capacity is Fargate standalone-task capacity; no ECS service or EC2
  container-instance fleet is present.

## Canonical Step Functions references

There are 26 live `edgartools-prod-*` Standard state machines. Every ECS task
reference resolves to this six-definition release cohort; no state machine was
observed referencing another task-definition revision:

| Runtime profile | Referenced revision | CPU / memory | Immutable image digest |
| --- | ---: | --- | --- |
| warehouse small | `edgartools-prod-small:166` | `512 / 1024` | `sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625` |
| warehouse medium | `edgartools-prod-medium:170` | `1024 / 4096` | `sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625` |
| warehouse large | `edgartools-prod-large:163` | `2048 / 8192` | `sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625` |
| MDM small | `edgartools-prod-mdm-small:143` | `512 / 1024` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |
| MDM medium | `edgartools-prod-mdm-medium:143` | `1024 / 4096` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |
| MDM large | `edgartools-prod-mdm-large:77` | `2048 / 8192` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |

All six use the production runner execution/task roles and log to
`/aws/ecs/edgartools-prod-warehouse`.

Profile use across state machines is consistent with the intended runtime
split: warehouse small handles daily-index utilities; warehouse medium handles
batch/seed work; warehouse large handles heavy warehouse/gold work; MDM small
handles migration/connectivity/count/verification stages; MDM medium handles
ordinary MDM work; and only `edgartools-prod-residual-holds-graph` references
MDM large.

## Image identity

| Role | ECR tags | Source tag commit | Pushed |
| --- | --- | --- | --- |
| warehouse | `warehouse-prod`, `warehouse-sha-e244a5712f65` | `e244a5712f65` | 2026-08-09 07:44 EDT |
| MDM | `mdm-prod`, `mdm-sha-1492ec26be2e` | `1492ec26be2e` | 2026-08-09 16:55 EDT |

The live runtime cohort is therefore not identical to repository commit
`96daa74e`: the warehouse and MDM images are deliberately role-specific builds
from earlier commits. In particular, current `main` contains later
`gold_verify` source/test changes not present in either image. A later ticket
must decide whether this is intended release composition or deployment drift;
the baseline ticket does not redeploy it.

## Active task-definition inventory

| Family | Active revisions | Oldest active | Latest active |
| --- | ---: | ---: | ---: |
| `edgartools-prod-small` | 88 | 79 | 166 |
| `edgartools-prod-medium` | 87 | 84 | 170 |
| `edgartools-prod-large` | 85 | 79 | 163 |
| `edgartools-prod-mdm-small` | 72 | 72 | 143 |
| `edgartools-prod-mdm-medium` | 69 | 75 | 143 |
| `edgartools-prod-mdm-large` | 69 | 9 | 77 |
| `edgartools-prod-silver-inspect` | 1 | 3 | 3 |
| `edgartools-prod-silver-repair` | 1 | 3 | 3 |

Total active revisions: 472. Step Functions reference six, leaving 466 active
revisions outside the current state-machine cohort. That is a cleanup
candidate set, not a safe deletion set: running/stopped-task history, rollback
cohorts, release manifests, and every external reference must be checked before
deregistration.

The two one-off silver utility families are not referenced by a live state
machine. Both use image digest
`sha256:575aa0f762095a2577dbefe763645b2815d975570a0e4bcb1f19b711e5671ee1`
and embed object-version-specific inspect/repair commands. They should be
reviewed for protected evidence or rollback use and then retired through the
guarded cleanup decision; they must not become general-purpose production
utilities.

## Post-handoff operator task evidence

The six most recent stopped tasks form one MDM validation cohort on the current
MDM revisions. Every container exited `0`:

| Command | Profile | Result |
| --- | --- | --- |
| `mdm migrate` | MDM small 143 | exit 0 |
| `mdm run --entity-type all --limit 5` | MDM medium 143 | exit 0 |
| `mdm backfill-relationships --limit 100` | MDM medium 143 | exit 0 |
| `mdm sync-graph --limit 100` | MDM medium 143 | exit 0 |
| `mdm verify-graph` | MDM small 143 | exit 0 |
| `mdm counts` | MDM small 143 | exit 0 |

These prove bounded command completion for the deployed MDM digest. They do
not prove full-volume throughput, every Step Functions workflow, end-to-end
gold completion, or that all old revisions are safe to deregister.

## Resulting frontier

This baseline unblocks these independent evidence tickets:

- Measure ECS Utilization by Workload Class.
- Reconcile Prod Task Definitions and Step Functions References.
- Inventory Every Production Workflow and Consumer.
- Measure Every Loop and Record Funnel.

Cleanup must flow through Reconcile Prod Task Definitions and Step Functions
References and Retire Stale Prod Revisions and Add Drift Gates. No live cleanup
was performed while establishing this baseline.
