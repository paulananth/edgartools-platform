# Data Issue Triage Guide

**Scope:** DASH-02 — operator first-inspection path for launch data issues.

This guide is the **first stop** when a data issue is observed during or after
launch. It covers all 8 DASH-02 layers: ingestion, bronze/silver, MDM, hosted
graph, dbt/gold, Native App, dashboard, and permissions.

**All diagnostic commands in this guide are read-only and non-destructive.**
No secrets, DSNs, passwords, tokens, raw connector exceptions, or stack traces
appear anywhere in this file. Placeholder tokens (`<DB>`, `<conn>`, `<role>`,
`<id>`) are used throughout — the operator supplies real identifiers at runtime
in a shell environment only.

---

## Routing Policy

Run the relevant CLI / dbt / Native App acceptance gate **first** and capture
pass/fail evidence. Use the dashboard to **inspect and explain** after gates
pass or to understand which gate is failing.

The dashboard (Overview, MDM Overview, Neo4j Overview, Mismatch Diagnostics)
is **inspection only** — it does not define acceptance. Failed CLI/dbt/Native
App gates are launch-blocking. Dashboard-only warnings block only when they
point to a failed gate.

This guide **extends** — and does not duplicate — the launch gate matrix
Data-Issue Triage Table (rows 90-100) at:

[`../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)

The matrix contains owner/blocker-status/next-action columns. This guide adds
**runnable read-only diagnostics** so an operator can follow this guide
start-to-finish without consulting other docs.

---

## Layer 1 — Ingestion

### Symptom

Missing or stale filing/entity input; Step Functions bootstrap or daily runs
show failed/timed-out executions or no recent successful runs.

### Likely Source

SEC API capture failure, Step Functions state machine error, or missing bronze
S3 objects at the expected path.

### Diagnostic

```bash
# 1. List recent Step Functions executions for the relevant state machine (read-only)
aws stepfunctions list-executions \
  --region us-east-1 \
  --state-machine-arn <STATE_MACHINE_ARN> \
  --max-results 5 \
  --query 'executions[*].{name:name,status:status,startDate:startDate}'

# 2. Confirm bronze S3 path has recent objects (read-only)
aws s3 ls s3://edgartools-dev-bronze-077127448006/warehouse/bronze/ \
  --recursive --human-readable | tail -20
```

### Owner

AWS operator

### Escalation

If executions show FAILED or TIMED_OUT: review CloudWatch task logs for the
failed execution (read-only log access) and document the error summary in
`evidence/aws.md`. Rerun a bounded capture only after the root cause is
identified. If the S3 path is empty, confirm the state machine was invoked and
check IAM ECS task role S3 write permissions.

---

## Layer 2 — Bronze / Silver

### Symptom

Bronze S3 objects exist but silver outputs (warehouse DuckDB shards) are
missing, stale, or incomplete; shard hydration produces empty tables.

### Likely Source

Warehouse transform failure, object-storage publish error, or shard hydration
not yet run after bronze capture.

### Diagnostic

```bash
# 1. List the warehouse storage root to confirm silver shard presence (read-only)
aws s3 ls s3://edgartools-dev-warehouse-077127448006/warehouse/ \
  --recursive --human-readable | grep -E '\.(duckdb|parquet)' | tail -20

# 2. Confirm bronze object count for a specific CIK prefix (read-only)
aws s3 ls s3://edgartools-dev-bronze-077127448006/warehouse/bronze/ \
  --recursive | grep "<CIK>" | wc -l
```

### Owner

AWS operator

### Escalation

If bronze exists but silver shards are absent: re-run bounded silver
preparation after confirming source evidence is present. Document command,
pass/fail, and object count summary in `evidence/aws.md`. Do not run
`gold-refresh` until silver shards are confirmed current.

---

## Layer 3 — MDM

### Symptom

Entity or relationship counts are missing, lower than expected, or inconsistent
with source data; `mdm counts` shows zero or near-zero rows.

### Likely Source

MDM Postgres DSN connectivity failure, MDM schema migration not applied, or
MDM entity population not yet completed against the current silver dataset.

### Diagnostic

```bash
# 1. Check entity and relationship counts in MDM Postgres (read-only)
edgar-warehouse mdm counts

# 2. Verify MDM secret container metadata (NEVER --query SecretString) (read-only)
aws secretsmanager describe-secret \
  --region us-east-1 \
  --secret-id <id> \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'
```

`mdm counts` is a read-only query against MDM Postgres. If the container
reports `LastChangedDate` but counts are zero, the secret may be populated but
MDM migration or run has not yet completed.

### Owner

MDM operator

### Escalation

If counts are zero: confirm `edgartools-<env>/mdm/postgres_dsn` has
`VersionIdsToStages.AWSCURRENT` populated (via `describe-secret` above). If
missing, follow the MDM secrets runbook at
`../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md` sections 1 and 5.
After secrets are confirmed, escalate to MDM operator to execute the
schema-migration and entity-population steps under a bounded run (these are
write operations, not diagnostics). Record non-secret count summary in
`evidence/mdm-hosted-graph.md`.

---

## Layer 4 — Hosted Graph

### Symptom

MDM entity/relationship counts exist but hosted graph nodes/edges or parity
checks fail; `verify-graph` reports mismatches or Native App connectivity
errors.

### Likely Source

Hosted graph synchronization not yet run, graph-ready Snowflake tables missing,
compute pool unavailable, or Native App grants incomplete.

### Diagnostic

```bash
# 1. Run strict hosted graph read-only verification (includes parity + Native App checks)
edgar-warehouse mdm verify-graph \
  --connection <conn> \
  --database <DB>
```

`verify-graph` is read-only. It checks graph parity (node/edge counts vs. MDM
Postgres), Native App availability (compute pool, BFS, WCC), and
GRAPH_INFO metadata — without syncing, modifying, or loading any data.

### Owner

MDM operator

### Escalation

If `verify-graph` reports parity failures: confirm that hosted graph
synchronization has been executed (MDM operator action — not a diagnostic).
If Native App checks fail (BFS, WCC, GRAPH_INFO), escalate to Layer 6 (Native
App) for compute pool and grant diagnosis. Record the non-secret parity summary
output in `evidence/mdm-hosted-graph.md`. A passing `verify-graph` is a
mandatory acceptance gate before the AWS MDM E2E can run.

---

## Layer 5 — dbt / Gold

### Symptom

Gold dynamic tables are stale, show no recent refresh timestamp, or disagree
with MDM/source data counts; `EDGARTOOLS_GOLD_STATUS` shows failed or aged
refresh entries.

### Likely Source

Snowflake native pull not yet running, dbt model SQL or config change not
deployed, dynamic-table grant gap, or `SNOWFLAKE_RUN_MANIFEST_TASK` not
started.

### Diagnostic

```bash
# 1. Query gold refresh status (read-only)
snow sql --connection <conn> \
  -q "SELECT * FROM <DB>.EDGARTOOLS_GOLD.PUBLIC.EDGARTOOLS_GOLD_STATUS ORDER BY REFRESHED_AT DESC LIMIT 10"

# 2. Confirm the manifest task is active (read-only)
snow sql --connection <conn> \
  -q "SHOW TASKS LIKE 'SNOWFLAKE_RUN_MANIFEST_TASK' IN DATABASE <DB>"
```

Both commands are read-only Snowflake queries. `EDGARTOOLS_GOLD_STATUS` records
last refresh time and model-level status. Task state `STARTED` confirms the
manifest task is active.

### Owner

Snowflake operator

### Escalation

If `EDGARTOOLS_GOLD_STATUS` shows aged or failed entries: check that
`SNOWFLAKE_RUN_MANIFEST_TASK` is `STARTED`. If models are stale after a SQL
change, a full-refresh redeploy of the dynamic table is required (Snowflake
operator action; see CLAUDE.md "dbt gold model SQL changes" section for the
`--full-refresh` command). If the refresh fails with a grant error, escalate to
Layer 8 (Permissions). Record status table output (no full row dumps) in
`evidence/snowflake.md`.

---

## Layer 6 — Native App

### Symptom

`verify-graph` fails on compute pool, `GRAPH_INFO`, `BFS`, or `WCC` checks;
Native App graph analytics jobs do not complete.

### Likely Source

Native App not installed or grants missing, compute pool suspended or
unavailable, or `SNOWFLAKE_RUN_MANIFEST_TASK` not started.

### Diagnostic

```bash
# 1. Check compute pool availability (read-only)
snow sql --connection <conn> \
  -q "SHOW COMPUTE POOLS"

# 2. Check application package and Native App installation (read-only)
snow sql --connection <conn> \
  -q "SHOW APPLICATION PACKAGES"
```

These are read-only Snowflake metadata queries. Also review the Native App
check section of `edgar-warehouse mdm verify-graph` output (Layer 4 above) —
it includes `GRAPH_INFO`, BFS, and WCC check results without running any
analytics jobs.

### Owner

Snowflake operator

### Escalation

If compute pool is `SUSPENDED` or `FAILED`: activate the pool via Snowflake
console (Snowflake operator action — not a diagnostic command). If the Native
App package is absent or has insufficient grants, apply the grants from
`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql` (Snowflake operator
action). After prerequisites are resolved, rerun `edgar-warehouse mdm
verify-graph` to confirm Native App checks pass before AWS E2E. Record compute
pool state and Native App name (not credentials) in `evidence/mdm-hosted-graph.md`.

---

## Layer 7 — Dashboard

### Symptom

Dashboard view shows stale counts, missing entity data, confusing copy, or
rendering errors in the Overview, MDM Overview, Neo4j Overview, or Mismatch
Diagnostics sections.

### Likely Source

Read-only dashboard helper payloads reflect upstream data state; stale gold
tables, missing MDM data, or an incomplete README rewrite are the most common
causes. Dashboard itself has no write controls.

### Diagnostic

```bash
# 1. Launch the read-only dashboard locally and inspect the four views
uv run --extra dashboard --extra mdm-runtime \
  streamlit run examples/mdm_graph_dashboard/streamlit_app.py

# 2. Run the read-only dashboard helper test coverage (read-only)
uv run pytest tests/mdm/test_dashboard_readonly.py -q
```

The dashboard is read-only — it has no destructive or write controls. View
inspection is the diagnostic. Passing `test_dashboard_readonly.py` confirms the
helper module is functional; view-level UAT is done by the operator.

### Owner

Dashboard reviewer

### Escalation

This layer is **WARNING** (not BLOCKED) unless the dashboard symptom points to
a failed acceptance gate (Layers 1-6). If stale counts: check Layer 5 (dbt/Gold)
freshness first. If entity data is missing: check Layer 3 (MDM) counts. If
rendering errors appear: check Streamlit console output for exceptions. Record
text UAT notes (no screenshots with sensitive data) in
`evidence/dashboard-security.md`. Escalate to `BLOCKED` only when the dashboard
issue traces to a failed CLI/dbt/Native App gate.

---

## Layer 8 — Permissions

### Symptom

A command succeeds as admin/ACCOUNTADMIN but fails as the deployer or runtime
role; dynamic-table INITIAL refresh fails with "not authorized"; IAM actions
succeed for `cli-access` but fail for ECS task role.

### Likely Source

Missing Snowflake direct `SELECT` grant on `EDGARTOOLS_SOURCE` tables (known
dev gap — see CLAUDE.md "Known gap blocking `--full-refresh`"), missing IAM
policy attachment on ECS task role, or Native App role grant gap.

### Diagnostic

```bash
# 1. Check Snowflake role grants (read-only)
snow sql --connection <conn> \
  -q "SHOW GRANTS TO ROLE <role>"

# 2. Check secret container metadata to confirm secret exists (METADATA ONLY — never --query SecretString)
aws secretsmanager describe-secret \
  --region us-east-1 \
  --secret-id <id> \
  --query '{Name:Name,ARN:ARN,LastChangedDate:LastChangedDate,VersionIdsToStages:VersionIdsToStages}'
```

`SHOW GRANTS TO ROLE` is a read-only Snowflake metadata query. `describe-secret`
returns name, ARN, and version metadata — never the secret value. Reading the
raw secret string from Secrets Manager is forbidden as a diagnostic (D-14);
use `describe-secret` metadata only.

### Owner

Snowflake operator (Snowflake RBAC); AWS operator (IAM)

### Escalation

If `SHOW GRANTS TO ROLE <role>` is missing a required grant: add the least-privilege
grant in the correct provisioning surface (`infra/snowflake/sql/bootstrap/` or
Terraform-managed `snowflake_grant_*` resources) and rerun the failing gate.
For the known `EDGARTOOLS_DEV_DEPLOYER` direct-SELECT gap on `EDGARTOOLS_SOURCE`,
see `TODOS.md` "EDGARTOOLS_DEV_DEPLOYER lacks direct SELECT on EDGARTOOLS_SOURCE".
Record grant summary (role name, object, privilege — no values) in
`evidence/snowflake.md`.

---

## Secret-Safety Note

**No mutation command and no raw-secret-retrieval command appears in this guide
as a runnable diagnostic.** Only `describe-secret` metadata
(`Name`, `ARN`, `LastChangedDate`, `VersionIdsToStages`) is safe to record as
evidence. Bounded count samples are diagnostics, not exhaustive exports. The
operator supplies real identifiers at runtime in a shell environment only —
never pasted into planning files or committed to this repository.

If a diagnostic reveals a credential, DSN, or token in its output: do not paste
that output into any evidence or planning file. Record the pass/fail status and
non-secret metadata only, per the secret-safety rules in the launch gate matrix.

---

## References

- [`../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md`](../01-production-readiness-inventory-and-launch-gate-contract/01-LAUNCH-GATE-MATRIX.md)
  — Data-Issue Triage Table (rows 90-100): owner, blocker status, and
  next-action columns that this guide extends with runnable read-only diagnostics.
- [`../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md`](../03-mdm-hosted-graph-e2e-acceptance/runbook/mdm-secrets.md)
  — MDM production secrets runbook: how to populate and verify `edgartools-<env>/mdm/postgres_dsn`
  and `edgartools-<env>/mdm/snowflake` secret containers (sections 1, 2, and 5).
- [`examples/mdm_graph_dashboard/README.md`](../../../../../examples/mdm_graph_dashboard/README.md)
  — Dashboard README: local launch instructions, Snowflake-hosted graph setup,
  and the four dashboard views.
- [`infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql`](../../../../../infra/snowflake/sql/neo4j_graph_analytics_app_grants.sql)
  — Native App grant SQL: apply when Native App compute pool or GRAPH_INFO checks
  fail in Layer 6.
