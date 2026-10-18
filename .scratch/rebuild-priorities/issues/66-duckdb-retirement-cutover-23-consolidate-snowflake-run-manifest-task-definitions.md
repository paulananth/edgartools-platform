# 23 — Keep one definition of `SNOWFLAKE_RUN_MANIFEST_TASK`

Status: done (#1076 merged 2026-10-18 12:51 ET).

Priority: 66, tier 4, housekeeping. Map: [Rebuild priorities](../map.md). Moved from `.scratch/duckdb-retirement-cutover/issues/23-consolidate-snowflake-run-manifest-task-definitions.md` on 2026-10-13; a Blocked by list of numbers now uses this map's numbers (or names the old effort); free text keeps the old effort's numbers.

**What was found:** while fixing Ticket 22 (deleted 2026-10-13, ticket 25; in git history)
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

## Answer (2026-10-18 12:39 ET)

1. Terraform owns the task. `deploy-snowflake-stack.sh` applies the Snowflake root (with the `native_pull` module) before the point where it replaced the task, so a fresh environment still gets it, started, on the 360-minute schedule; `install.sh` reaches the task only through that script. Without `native_pull` there is no manifest stream for the task to read, so nothing is lost.
2. `04_refresh_wrapper.sql` keeps the two procedures (`REFRESH_AFTER_LOAD`, `PROCESS_RUN_MANIFEST_STREAM`) and loses the task and its `RESUME`; its header names Terraform as the task's owner. No script runs the file.
3. The Question asked for one test; two remain, on purpose: the Terraform test keeps the UTC pin on the one definition, and the two copy-checks became one test: no bootstrap SQL file and no `infra/scripts` script creates the task (on main it names `04_refresh_wrapper.sql` and `deploy-snowflake-stack.sh`; on this branch none). The Terraform test keeps the UTC pin.

## Checklist

- [x] GoF consult: three copies of one task are a real change axis (the UTC pin touched all three; the schedule change reached one); the fix is deletion to one owner, no pattern (2026-10-18 12:39 ET)
- [x] `deploy_manifest_task` and its call deleted from `deploy-snowflake-stack.sh`; the header says Terraform creates the task (2026-10-18 12:39 ET)
- [x] The task block deleted from `04_refresh_wrapper.sql`, procedures kept; Terraform's comment says it is the one definition (2026-10-18 12:39 ET)
- [x] One test that only Terraform creates the task, shown to name both old copies on main; `test_loader_task_timezone_sql.py` and `test_install_wizard.py` pass (38); `bash -n` clean (2026-10-18 12:39 ET)
- [x] Three-axis review (2026-10-18 12:44 ET): Standards found an unused constant and a long line (fixed); Spec asked the answer to say why two tests remain (said) and noted a one-line regex; GoF asked for a wider search: the test now reads every `.sql`, `.sh` and `.py` under `infra/` and spans lines (on main it names both old copies; here none). GoF also found `04`'s two procedures duplicated by Terraform with different bodies: ticket 109
- [x] PR, CI green, merged on green: #1076, merged 2026-10-18 12:51 ET
- [ ] ~~Prod run~~ skipped, none is needed: nothing runs against prod in this change; the next `install.sh` run no longer moves the task's schedule
- [x] Learning → skill: none; the test (only Terraform creates the task) holds the rule, and CLAUDE.md's "Provisioning that isn't Terraform" rule already says it
