# Post-Launch Monitoring Activation — v1.6

> **Non-secret deliverable.** This file contains no credential values, no raw AWS account
> IDs, no full ARNs, no Snowflake passwords, no DSN user credentials, no private-key
> material, and no generated deployment JSON bodies. Secret names (e.g.,
> `edgartools-prod/mdm/postgres_dsn`) are cited as identifiers only; secret values are
> never included. All diagnostic commands listed below are READ-ONLY.

**Date:** 2026-06-26
**Plan:** 11-02
**Scope:** v1.6 Production Launch — post-GO monitoring activation record (OPS-03)

---

## Purpose

This document is the v1.6 activation record for post-launch monitoring. It does **not**
duplicate the v1.5 monitoring checklist body — it references it and extends it with:

1. Named owners for each of the 8 OPS-02 monitoring systems
2. First-run read-only check commands per system
3. A dedicated first-run watch item for `BatchSilver MaxConcurrency=4` (Blocker 4 open item)
4. A reference to the v1.5 rollback/resume runbook for stop conditions (OPS-03)

**v1.5 monitoring checklist (base document):**
`milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/post-launch-monitoring.md`

Read the v1.5 checklist for the full per-system diagnostic detail, expected output shape, and
escalation threshold. This document names owners and adds the v1.6 MaxConcurrency watch.

---

## 8 OPS-02 Systems — Named Owners and First-Run Checks

### System 1: Step Functions execution status

**Owner:** AWS operator

**First-run read-only check:**
```bash
aws stepfunctions list-executions \
  --state-machine-arn <arn> \
  --status-filter RUNNING \
  --query 'executions[].{name:name,status:status,startDate:startDate}'

aws stepfunctions describe-execution \
  --execution-arn <arn> \
  --query status
```

**Healthy:** execution reaches `SUCCEEDED`; no unexpected concurrent `RUNNING` executions
of the same state machine.

**Escalate:** `FAILED`, `TIMED_OUT`, or `ABORTED` when operator did not request a stop.

---

### System 2: CloudWatch logs

**Owner:** AWS operator

**First-run read-only check:**
```bash
aws logs tail <log-group> --since 1h
```

**Healthy:** lifecycle messages with no `ERROR`/`CRITICAL`/traceback lines.

**Escalate:** repeated `ERROR`/`CRITICAL` lines, unhandled exception, or silent gap in
expected lifecycle log lines (task silently hung).

---

### System 3: Snowflake task history

**Owner:** Snowflake operator

**First-run read-only check:**
```bash
snow sql --connection <conn> \
  -q "SELECT * FROM TABLE(<DB>.INFORMATION_SCHEMA.TASK_HISTORY()) ORDER BY SCHEDULED_TIME DESC LIMIT 10;"

snow sql --connection <conn> \
  -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK';"
```

**Healthy:** `STATE = SUCCEEDED` for recent rows; `SNOWFLAKE_RUN_MANIFEST_TASK` in
state `started`; manifest pickup within ~1 minute of gold-refresh export.

**Escalate:** any `STATE = FAILED`; `SNOWFLAKE_RUN_MANIFEST_TASK` not in state `started`;
no new task run appears within expected post-export window.

---

### System 4: dbt test failures

**Owner:** Snowflake operator

**First-run read-only check:**
```bash
uv run --with dbt-snowflake dbt test --target prod
```

**Healthy:** "Completed successfully" with `0 errors, 0 warnings`.

**Escalate:** any `FAIL` or `ERROR`, especially on gold tables consumed by the dashboard
(`company`, `ownership_holdings`, `ownership_activity`, `filing_detail`, `filing_activity`,
`adviser_disclosures`, `adviser_offices`, `private_funds`, `ticker_reference`,
`edgartools_gold_status`).

---

### System 5: MDM counts

**Owner:** MDM operator

**First-run read-only check:**
```bash
edgar-warehouse mdm counts
```

**Healthy:** non-zero entity and relationship counts consistent with universe size; counts
trending upward as new filings land, never dropping to zero unexpectedly.

**Escalate:** any expected entity/relationship count is zero or near-zero after a run that
should have populated it, or counts drop significantly from prior known-good without a
corresponding scope change.

---

### System 6: Hosted graph verification

**Owner:** MDM operator

**First-run read-only check:**
```bash
edgar-warehouse mdm verify-graph
```

**Healthy:** parity report with no count mismatches; Native App check (`GRAPH_INFO`,
`BFS`, `WCC`) reports reachable/healthy.

**Escalate:** any parity mismatch between MDM counts and hosted graph; Native App check
fails on `GRAPH_INFO`, `BFS`, or `WCC`.

---

### System 7: Native App compute pool health

**Owner:** Snowflake operator

**First-run read-only check:**
```bash
snow sql --connection <conn> -q "SHOW COMPUTE POOLS;"
```

**Healthy:** the pool backing the hosted graph Native App in state `ACTIVE` or `IDLE`.

**Escalate:** pool `SUSPENDED` when graph queries are expected; pool stuck in transitional
state (`STARTING`/`STOPPING`) beyond a few minutes; correlates with `verify-graph` failure.

---

### System 8: Dashboard availability

**Owner:** Dashboard reviewer

**First-run read-only check:**
```bash
pgrep -f streamlit
```

(or a health-check HTTP probe against the configured health endpoint — no write/POST calls.)

**Healthy:** `pgrep -f streamlit` returns one PID; health URL returns HTTP `200`.

**Escalate:** no PID when dashboard is expected running; health URL returns non-`200` or
times out.

---

## First-Run Watch: BatchSilver MaxConcurrency=4

**Tied to:** Blocker 4 open item in `11-AUDIT.md` and `11-GO-NO-GO-PACKET.md`

**Background:** The deployed `BatchSilver` Distributed Map step runs at `MaxConcurrency=4`
(set in `infra/scripts/deploy-aws-application.sh` as of commit `219619c`). The committed
end-to-end evidence (`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md`)
validates only `MaxConcurrency=2` (execution `bronze-seed-silver-gold-1782351277`). The
`MaxConcurrency=4` value is deployed but not yet evidence-validated at scale.

**Watch items for the first live `bronze_seed_silver_gold` run at MaxConcurrency=4:**

1. **DuckDB write-contention errors.** If multiple ECS tasks attempt concurrent writes to
   the same `silver.duckdb` monolith file, DuckDB may raise a lock error or produce a
   partial/corrupt write. Check CloudWatch logs for the `BatchSilver` window (System 2
   above) for any log line containing `lock`, `database is locked`, `concurrent`, or
   `DuckDB error`.

2. **Duplicate or partial filing rows.** After the run completes, compare the MDM counts
   (System 5 above) against the prior known-good count. Unexpected large gaps or
   duplicated CIK-accession rows in silver are a symptom of concurrent write-contention.

3. **Shard-manifest fallback.** If the silver reader falls back from a shard manifest to
   the monolith `silver.duckdb` for any batch, that fallback path accumulates concurrent
   write pressure. Watch for log lines containing `fallback` or `missing shard manifest`.

**Remediation if symptoms appear:**

Revert `BatchSilver MaxConcurrency` to `2` in `infra/scripts/deploy-aws-application.sh`
and redeploy. Do NOT keep running at `MaxConcurrency=4` if DuckDB lock errors or duplicate
rows are observed. File an issue to validate `MaxConcurrency=4` safely (WAL-mode or shard
manifest per batch) before re-enabling it.

**Resolution:** Once a complete `bronze_seed_silver_gold` run at `MaxConcurrency=4` has
succeeded (all seven stages SUCCEEDED, 81/81 batches, zero `sec_pull_started`, zero
write-contention symptoms), append a sanitized addendum to
`phases/09-production-hosted-graph-e2e/evidence/aws-mdm-e2e.md` and commit it. This
closes the Blocker 4 open item and upgrades it from CONDITIONAL to PASS in the audit record.

---

## Rollback / Resume Reference (OPS-03)

For stop conditions, safe mid-run cancellation, and resume-from-checkpoint procedures:

`milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md`

The rollback/resume runbook documents:
- When and how to cancel a running Step Functions execution safely
- State to check before resuming after an aborted run
- Bounded stop conditions required by OPS-03

---

## Secret-Safety Note

All diagnostic commands above are read-only assertions. None of the following commands
appear as runnable commands in this file:

- Secret-write commands (`put-secret-value`, `get-secret-value --query SecretString`) never appear here as runnable commands.
- MDM mutation commands (`sync-graph`, `migrate`, `run`, `derive`, `load`) never appear here as runnable commands — only `mdm counts` and `mdm verify-graph` (read-only).
- Build commands (`dbt run`, `dbt build`) never appear here as runnable commands — only `dbt test` (read-only assertion).
- Infrastructure mutation commands (`terraform apply`, `terraform destroy`) never appear here as runnable commands.
- Storage deletion commands (`aws s3 rm`, `--delete` flag) never appear here as runnable commands.

If a diagnostic command's output unexpectedly contains a credential, DSN, or token: do
not paste that output into any evidence or planning file. Record only pass/fail status
and non-secret metadata.

---

## References

- `milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/post-launch-monitoring.md` — base v1.5 monitoring checklist (full per-system detail, escalation thresholds)
- `milestones/v1.5-phases/05-go-no-go-launch-evidence-and-handoff/runbook/launch-ops.md` — stop/rollback/resume procedures (OPS-03)
- `phases/11-final-go-decision-and-launch-evidence-handoff/11-AUDIT.md` — v1.6 evidence audit; Blocker 4 CONDITIONAL detail and open items
- `phases/11-final-go-decision-and-launch-evidence-handoff/11-GO-NO-GO-PACKET.md` — v1.6 go/no-go decision packet; Blocker 4 open-item resolution options
- `milestones/v1.5-phases/01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md` — authoritative Owner column, Data-Issue Triage Table, Secret-Safety Rules
