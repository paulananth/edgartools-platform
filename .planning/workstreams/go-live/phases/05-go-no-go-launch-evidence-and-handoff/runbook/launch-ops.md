# Launch Ops — Stop and Rollback Runbook

**Scope:** OPS-01 (D-03) — the single stop/rollback path for the first
production launch run.

This is the launch stop/rollback runbook for the first production run of the
v1.5 go-live milestone. **All commands documented here are read-only checks
or bounded-stop commands.** There are no destructive, delete, secret-write,
or destructive Terraform commands anywhere in this file. No secrets, DSNs,
passwords, tokens, ARNs, or raw exceptions appear anywhere below. Placeholder
tokens (`<arn>`, `<conn>`, `<task>`, `<DB>`, `<pid>`) are used throughout —
the operator supplies real identifiers at runtime in a shell environment only.

This runbook covers all four systems involved in the production launch
sequence: AWS Step Functions, Snowflake tasks/dbt, MDM runs, and the
dashboard. Use it when a running production workload needs to be stopped
safely, when confirming a stop took effect, when deciding whether a rerun is
safe, and when inspecting what state a stop leaves behind.

---

## 1. AWS Step Functions

### Stop command

Stop a running execution. For a Distributed Map state, stopping the parent
execution aborts the child map runs as well — there is no separate command
needed for the map children.

```bash
aws stepfunctions stop-execution \
  --execution-arn <arn>
```

### Verify stopped

```bash
# Confirm the stopped execution shows ABORTED
aws stepfunctions describe-execution \
  --execution-arn <arn> \
  --query status

# Confirm no other executions of the same state machine are still RUNNING
aws stepfunctions list-executions \
  --state-machine-arn <arn> \
  --status-filter RUNNING
```

### Safe resume/rerun

SEC filing artifacts are additive and immutable once captured. Warehouse
loaders skip already-loaded files by default and only re-fetch when an
operator passes an explicit `--force` repair flag. This means a rerun after a
clean abort is safe by default: it will not re-fetch or duplicate bronze data
that was already written by the aborted run. Confirm the prior execution
shows `ABORTED` (not `RUNNING`) before starting a new execution of the same
state machine.

### Rollback scope

- Bronze S3 files already written by the aborted execution persist — they are
  additive and immutable, so stopping the execution does not undo them.
- Inspect what was written so far with a read-only listing:
  ```bash
  aws s3 ls s3://<bucket>/warehouse/bronze/...
  ```
- No bronze data needs to be manually rolled back; a subsequent rerun (or the
  next scheduled run) picks up where loading left off because loaders skip
  already-loaded files by default.

---

## 2. Snowflake tasks / dbt

### Stop command

Suspend a running or scheduled Snowflake task. This is a bounded suspend — it
does not drop the task, drop any table, or mutate any row.

```bash
snow sql --connection <conn> \
  -q "ALTER TASK <task> SUSPEND;"
```

### Verify stopped

```bash
# Confirm the task's state column shows suspended
snow sql --connection <conn> \
  -q "SHOW TASKS LIKE '<task>';"
```

### Safe resume/rerun

Suspending a task is always safe to do and always safe to undo — it leaves
the last successful refresh of the dynamic table in place. If a dynamic-table
refresh failed mid-run, recover by re-running dbt against the same target
following [`runbook/dbt-gold.md`](../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md)
(link, not pasted here). Before re-running dbt, confirm freshness and current
status read-only:

```bash
snow sql --connection <conn> \
  -q "SELECT * FROM <DB>.EDGARTOOLS_GOLD.EDGARTOOLS_GOLD_STATUS LIMIT 10;"
```

### Rollback scope

- Suspending a task leaves the dynamic table at its last successful refresh
  state — no rows are dropped and no data is lost by suspending.
- A failed `INITIAL` or incremental refresh does not partially commit; the
  dynamic table either reflects the prior successful refresh or the new one,
  never a half-applied state.
- Inspect current state with the read-only `SHOW TASKS` and
  `EDGARTOOLS_GOLD_STATUS` queries above before deciding whether to resume.

---

## 3. MDM runs

### Stop command

An MDM E2E run is itself driven by a Step Functions execution. Abort it the
same way as any other Step Functions execution:

```bash
aws stepfunctions stop-execution \
  --execution-arn <arn>
```

### Verify stopped

```bash
# Confirm ABORTED status
aws stepfunctions describe-execution \
  --execution-arn <arn> \
  --query status

# Read-only entity/relationship counts after the abort, to see what
# was derived before the stop
edgar-warehouse mdm counts
```

### Safe resume/rerun

The MDM pipeline is re-runnable after a clean abort once connectivity and
counts are confirmed. Use the read-only verify-graph check as the precondition
for a safe rerun — if it reports parity, the graph state is consistent enough
to resume from:

```bash
edgar-warehouse mdm verify-graph
```

Migrations applied by `mdm migrate` are forward-only and are not undone by an
abort, so a rerun does not attempt to re-apply already-applied migrations.

### Rollback scope

- An applied MDM database migration persists after an abort — migrations are
  forward-only and are not rolled back by stopping the execution.
- A partially completed run can leave partial derived relationships (for
  example partial `IS_INSIDER` or `MANAGES_FUND` edges). A full rerun
  overwrites these partial results rather than leaving them stale — the MDM
  derivation steps are designed to recompute fully on each run.
- Inspect what was derived so far with the read-only `mdm counts` command
  above before deciding whether to rerun immediately or investigate first.

---

## 4. Dashboard

### Stop command

The dashboard is read-only against Snowflake/MDM and writes no state of its
own. Stop the local Streamlit process by name or PID:

```bash
pkill -f streamlit
# or, for a specific process:
kill <pid>
```

### Verify stopped

```bash
# Confirm no Streamlit process remains
pgrep -f streamlit
```
An empty result (no PID printed) confirms the process is stopped.

### Safe resume/rerun

The dashboard can be relaunched at any time — it holds no state between runs
and performs no writes to Snowflake, MDM, or S3. There is no precondition
beyond having a valid read-only connection configured.

### Rollback scope

- **None.** The dashboard is read-only: it issues `SELECT`-only queries
  against Snowflake gold tables and read-only MDM/hosted-graph checks, and it
  writes no state anywhere. Stopping the Streamlit process leaves nothing to
  roll back.
- This is explicitly confirmed here so an operator does not spend time
  looking for rollback steps that do not exist for this system.

---

## Secret-Safety Note

This runbook documents only read-only checks and bounded-stop commands.

- No `put-secret-value` command appears anywhere in this file as a runnable
  command.
- No `get-secret-value --query SecretString` command appears anywhere in this
  file as a runnable command.
- No `aws s3 rm` command and no `--delete` flag usage appears anywhere in this file as a runnable command.
- No destructive Terraform command (`terraform apply` or `terraform destroy`) appears anywhere in this file as a runnable command.
- Secret NAMES (for example `edgartools-prod/mdm/postgres_dsn`) may appear in
  cross-references to other runbooks; secret VALUES never appear in this file
  or any file it links to.

If a stop or verify command's output unexpectedly contains a credential, DSN,
or token: do not paste that output into any evidence or planning file. Record
only the pass/fail status and non-secret metadata, per the Secret-Safety
Rules in the launch gate matrix.

---

## References

- [`../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)
  — authoritative per-gate list and full Secret-Safety Rules section.
- [`../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md`](../02-aws-and-snowflake-production-deployment-dry-run/runbook/aws-deploy.md)
  — AWS production deploy procedure this runbook's Step Functions stop path complements.
- [`../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md`](../02-aws-and-snowflake-production-deployment-dry-run/runbook/dbt-gold.md)
  — dbt run/test procedure referenced for Snowflake task recovery above.
- [`../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md`](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md)
  — MDM production secrets runbook; populate secrets before any MDM rerun that needs them.
- [`../05-GO-NO-GO-PACKET.md`](../05-GO-NO-GO-PACKET.md)
  — companion go/no-go launch decision packet; this runbook is the "how to
  stop safely" companion to its production launch sequence.
