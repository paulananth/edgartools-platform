# Post-Launch Monitoring — First Production Run Checklist

**Scope:** OPS-02 (D-04) — the post-launch monitoring and incident checklist
for the first production run of the v1.5 go-live milestone.

This is the operator's "watch the first prod run" checklist. **All
diagnostic commands documented here are read-only.** There are no
destructive, delete, secret-write, or mutation commands anywhere in this
file. No secrets, DSNs, passwords, tokens, ARNs, or raw exceptions appear
anywhere below. Placeholder tokens (`<arn>`, `<conn>`, `<DB>`, `<log-group>`,
`<role>`) are used throughout — the operator supplies real identifiers at
runtime in a shell environment only. Secret NAMES (for example
`edgartools-prod/mdm/postgres_dsn`) may appear in cross-references; secret
VALUES never appear in this file.

This checklist covers exactly the 8 OPS-02 systems, in order: (1) Step
Functions status, (2) CloudWatch logs, (3) Snowflake task history, (4) dbt
test failures, (5) MDM counts, (6) hosted graph verification, (7) Native App
compute pool health, (8) dashboard availability. Each section below carries
a read-only diagnostic, the expected healthy output shape, the escalation
threshold, and the named escalation owner.

---

## 1. Step Functions status

### Diagnostic

```bash
aws stepfunctions list-executions \
  --state-machine-arn <arn> \
  --status-filter RUNNING \
  --query 'executions[].{name:name,status:status,startDate:startDate}'

aws stepfunctions describe-execution \
  --execution-arn <arn> \
  --query status
```

### Expected output shape

A short list of currently RUNNING executions (ideally zero or one for the
first prod run), each with a `name` and `startDate`; `describe-execution`
returns one of `RUNNING`, `SUCCEEDED`, `FAILED`, `TIMED_OUT`, or `ABORTED`.
For a healthy first run, the targeted execution eventually reports
`SUCCEEDED` and no unexpected concurrent executions of the same state
machine appear.

### Escalation threshold

Escalate if `describe-execution` reports `FAILED`, `TIMED_OUT`, or
`ABORTED` when the operator did not request a stop, or if
`list-executions` shows more concurrent `RUNNING` executions of the same
state machine than the launch sequence intended to start.

### Owner

AWS operator (mirrors the launch gate matrix Owner column for AWS
application deploy / AWS MDM hosted graph E2E rows).

---

## 2. CloudWatch logs

### Diagnostic

```bash
aws logs tail <log-group> --since 1h
```

### Expected output shape

A bounded stream of recent log lines from the ECS task's log group, showing
normal lifecycle messages (task start, stage transitions, completion) with
no `ERROR`/`CRITICAL`/traceback lines. Volume should be proportional to the
batch size of the run in progress.

### Escalation threshold

Escalate if the tail shows repeated `ERROR`/`CRITICAL` lines, an unhandled
exception/traceback, or a gap where expected lifecycle log lines stop
appearing entirely (task silently hung).

### Owner

AWS operator.

---

## 3. Snowflake task history

### Diagnostic

```bash
snow sql --connection <conn> \
  -q "SELECT * FROM TABLE(<DB>.INFORMATION_SCHEMA.TASK_HISTORY()) ORDER BY SCHEDULED_TIME DESC LIMIT 10;"

snow sql --connection <conn> \
  -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK';"
```

### Expected output shape

`TASK_HISTORY()` returns up to 10 recent rows with `STATE` of `SUCCEEDED` for
the most recent runs, and `SCHEDULED_TIME`/`COMPLETED_TIME` close together
(no runs stuck in `EXECUTING` far past their expected duration). `SHOW TASKS`
shows `SNOWFLAKE_RUN_MANIFEST_TASK` in state `started`.

### Escalation threshold

Escalate if the most recent `TASK_HISTORY()` rows show `STATE = 'FAILED'`,
or if `SNOWFLAKE_RUN_MANIFEST_TASK` is not in state `started`, or if no new
task run appears within the expected post-export window (manifest pickup
should occur within about 1 minute of a gold-refresh export per CLAUDE.md).

### Owner

Snowflake operator.

---

## 4. dbt test failures

### Diagnostic

```bash
uv run --with dbt-snowflake dbt test --target prod
```

### Expected output shape

A summary line reporting the total number of tests run and a `PASS` count
equal to the total (for example "Completed successfully" with `0 errors,
0 warnings`). This is a read-only assertion run — it issues `SELECT`-style
checks only and performs no writes.

### Escalation threshold

Escalate if any test reports `FAIL` or `ERROR`, particularly tests on the
gold tables consumed by the dashboard (`company`, `ownership_holdings`,
`ownership_activity`, `filing_detail`, `filing_activity`,
`adviser_disclosures`, `adviser_offices`, `private_funds`,
`ticker_reference`, `edgartools_gold_status`).

### Owner

Snowflake operator.

---

## 5. MDM counts

### Diagnostic

```bash
edgar-warehouse mdm counts
```

### Expected output shape

A read-only summary of entity and relationship counts (companies, insiders,
advisers, `IS_INSIDER`, `MANAGES_FUND`, `HOLDS`, `COMPANY_HOLDS`,
`INSTITUTIONAL_HOLDS` edges, etc.) consistent with the universe size loaded
so far — counts should be non-zero and trending upward as new filings land,
never unexpectedly dropping to zero between runs.

### Escalation threshold

Escalate if any expected entity/relationship count is zero or near-zero
after a run that should have populated it, or if counts drop significantly
from the prior known-good count without a corresponding universe scope
change.

### Owner

MDM operator.

---

## 6. Hosted graph verification (`verify-graph`)

### Diagnostic

```bash
edgar-warehouse mdm verify-graph
```

### Expected output shape

A read-only strict parity report comparing MDM-derived relationship counts
against the hosted Snowflake graph (nodes/edges), plus a Native App check
section (`GRAPH_INFO`, `BFS`, `WCC`) reporting reachable/healthy. A passing
run reports parity with no count mismatches and no Native App procedure
errors.

### Escalation threshold

Escalate if `verify-graph` reports any parity mismatch between MDM counts
and the hosted graph, or if the Native App check section fails on
`GRAPH_INFO`, `BFS`, or `WCC` (compute pool unavailable, procedure error, or
stale graph).

### Owner

MDM operator.

---

## 7. Native App compute pool health

### Diagnostic

```bash
snow sql --connection <conn> -q "SHOW COMPUTE POOLS;"
```

### Expected output shape

A read-only listing of compute pools with `STATE` of `ACTIVE` or `IDLE` for
the pool backing the hosted graph Native App, and no pool stuck in
`SUSPENDED`, `STOPPING`, or showing repeated `STARTING` without reaching
`ACTIVE`.

### Escalation threshold

Escalate if the relevant compute pool is `SUSPENDED` when graph queries are
expected to run, or remains in a transitional state (`STARTING`/`STOPPING`)
beyond a few minutes, or if `verify-graph`'s Native App check (item 6 above)
fails in a way that correlates with compute pool state.

### Owner

Snowflake operator.

---

## 8. Dashboard availability

### Diagnostic

```bash
pgrep -f streamlit
```

(or, if a hosted health-check URL is configured for the deployment, a
read-only HTTP probe against that URL's health endpoint — no write/POST
calls.)

### Expected output shape

`pgrep -f streamlit` returns one PID (the running dashboard process); a
health-check URL probe returns HTTP `200` with a healthy status payload.

### Escalation threshold

Escalate if `pgrep -f streamlit` returns no PID when the dashboard is
expected to be running, or a configured health-check URL returns a
non-`200` status or times out.

### Owner

dashboard reviewer.

---

## Cross-Reference: Escalation Owners and Triage Routing

Escalation owners and per-layer routing in this checklist mirror the Owner
column and the Data-Issue Triage Table in the launch gate matrix:
[`../../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`](../../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md).
This checklist EXTENDS that table with a post-launch monitoring cadence (what
to run, how often, and what "healthy" looks like during the first production
run) — it does not duplicate the matrix's blocker/status columns. When a
diagnostic above surfaces a symptom that matches a row in the Data-Issue
Triage Table, follow that table's "Next action" column rather than improvising
a new remediation here.

---

## Secret-Safety Note

This checklist documents only read-only diagnostic commands.

- No `put-secret-value` command appears anywhere in this file as a runnable
  command.
- No `get-secret-value --query SecretString` command appears anywhere in
  this file as a runnable command.
- No `mdm sync-graph`, `mdm migrate`, `mdm run`, `mdm derive`, or `mdm load`
  command appears anywhere in this file as a runnable command — only the
  read-only `mdm counts` and `mdm verify-graph` diagnostics above.
- No `dbt run` or `dbt build` command appears anywhere in this file as a
  runnable command — only the read-only `dbt test` assertion above.
- No `terraform apply` or `terraform destroy` command appears anywhere in
  this file as a runnable command.
- No `aws s3 rm` command and no `--delete` flag usage appears anywhere in
  this file as a runnable command.
- Secret NAMES (for example `edgartools-prod/mdm/postgres_dsn`) may appear
  in cross-references to other runbooks; secret VALUES never appear in this
  file or any file it links to.

If a diagnostic command's output unexpectedly contains a credential, DSN, or
token: do not paste that output into any evidence or planning file. Record
only the pass/fail status and non-secret metadata, per the Secret-Safety
Rules in the launch gate matrix.

---

## References

- [`../../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`](../../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)
  — authoritative per-gate list, Owner column, Data-Issue Triage Table, and
  full Secret-Safety Rules section.
- [`../../04-operator-dashboard-and-data-issue-triage/runbook/data-issue-triage.md`](../../04-operator-dashboard-and-data-issue-triage/runbook/data-issue-triage.md)
  — 8-layer data-issue triage guide for diagnosing dashboard-surfaced
  symptoms back to root cause.
- [`../05-GO-NO-GO-PACKET.md`](../05-GO-NO-GO-PACKET.md)
  — companion go/no-go launch decision packet; this checklist is the "watch
  the first prod run" companion to its production launch sequence.
- [`launch-ops.md`](launch-ops.md)
  — companion stop/rollback runbook; use it when a diagnostic above
  indicates a running workload needs to be stopped safely.
