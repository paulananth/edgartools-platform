# 23 — Keep one definition of `SNOWFLAKE_RUN_MANIFEST_TASK`

**What was found:** while fixing [Ticket 22](22-silver-landing-timestamps-shifted-by-account-timezone.md)
(2026-09-14). The task that loads the source layer and refreshes gold is created in three places,
and each one replaces the task entirely, so whichever runs last wins:

| Definition | `SCHEDULE` | Last changed |
|---|---|---|
| Terraform `snowflake_task.manifest_processor` (`infra/terraform/snowflake/modules/native_pull/main.tf`) | 360 minutes | `b4f2356a`, 2026-08-14 (credit economy) |
| `deploy_manifest_task` in `infra/scripts/deploy-snowflake-stack.sh` (`CREATE OR REPLACE TASK`, run by `install.sh` after Terraform) | 1 minute | `c19545d3`, 2026-05-10 |
| `infra/snowflake/sql/bootstrap/04_refresh_wrapper.sql` (`CREATE OR REPLACE TASK`, no script runs it) | none | — |

Live prod (2026-09-14): 360 minutes, created 2026-08-18. So the 2026-08-14 schedule change reached
only Terraform: the next `install.sh` run would put the task back on a 1-minute schedule (the cost
the change removed), and the `04` file would create a standalone task with no schedule at all.
Ticket 22 had to add `TIMEZONE = 'UTC'` to all three copies, held together only by
`tests/unit/test_loader_task_timezone_sql.py`.

## Question

Make one definition own the task (likely Terraform, which matches prod) and remove the other two
`CREATE OR REPLACE TASK` blocks. Decide:

1. Which install/deploy path must still create the task on a fresh environment, and whether
   removing `deploy_manifest_task` changes that (its comment says the task "is not managed by
   Terraform", which is no longer true).
2. What `04_refresh_wrapper.sql` keeps (the procedure bodies) and loses (the task block).
3. Collapse the three manifest-task tests in `test_loader_task_timezone_sql.py` into one.

**Blocked by:** none. Changes deploy behaviour, so it needs its own review and operator go-ahead
before any prod run.
