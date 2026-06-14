# Roadmap: Go Live

workstream: go-live
status: active
milestone: v1.5 Go Live
updated: 2026-06-14

---

## Milestone Goal

Prepare the AWS-first EdgarTools Platform for production go-live by proving the launch
gates for AWS deployment, Snowflake native pull and gold, MDM Snowflake Postgres,
Snowflake-hosted graph verification, dashboard inspection, secret-safe evidence, and
operator handoff.

---

## Phases

- [x] **Phase 1: Production Readiness Inventory And Launch Gate Contract** - define the go/no-go checklist, reconcile existing workstream evidence, inventory production prerequisites, and set the evidence and secret-safety rules. (completed 2026-06-14)
- [ ] **Phase 2: AWS And Snowflake Production Deployment Dry Run** - validate production AWS application deployment readiness, Snowflake native pull, dbt gold, and gold freshness evidence through existing scripts and commands.
- [ ] **Phase 3: MDM Hosted Graph E2E Acceptance** - prove production MDM Snowflake Postgres, hosted graph sync, strict Native App verification, and AWS MDM E2E acceptance without external Neo4j credentials.
- [ ] **Phase 4: Operator Dashboard And Data Issue Triage** - make the dashboard and runbook the operator inspection path for MDM, hosted graph, gold, and data quality issues.
- [ ] **Phase 5: Go/No-Go Launch, Evidence, And Handoff** - assemble final evidence, run launch approval, document rollback or stop paths, and hand off post-launch monitoring.

---

## Phase Details

### Phase 1: Production Readiness Inventory And Launch Gate Contract

**Goal**: Operators have a concrete production launch checklist, evidence template, and blocker inventory before any expensive or state-changing launch run begins.

**Depends on**: Current merged main and the existing workstream evidence from `neo4j-snowflake`, `mdm-neo4j-dashboard`, and `neo4j-pipe`.

**Requirements**: LIVE-01, SEC-01, ISO-01, ISO-02

**Success Criteria** (what must be TRUE):

1. Launch gates list every required AWS, Snowflake, MDM, hosted graph, dashboard, and dbt check with the command or evidence source.
2. Existing dev proof is reconciled against production launch needs, including hosted graph E2E, dashboard UAT, MDM DSN source, and unresolved workstream closeout items.
3. Secret-safety rules explicitly forbid DSNs, passwords, tokens, Terraform state, raw connector traces, and sensitive generated deployment values in evidence.
4. Production blockers are classified as launch-blocking, warning-only, or deferred with owner and remediation.
5. Work remains isolated to the go-live workstream unless a later phase explicitly plans code or runbook edits.

**Plans**: TBD

### Phase 2: AWS And Snowflake Production Deployment Dry Run

**Goal**: Operators can prove production deployment readiness for AWS active components, Snowflake native pull, and dbt gold through existing scripts and non-secret evidence.

**Depends on**: Phase 1

**Requirements**: LIVE-02, SNOW-01, SNOW-02

**Success Criteria** (what must be TRUE):

1. Production AWS passive infrastructure outputs and generated application deployment summary are present or the missing items are documented as launch blockers.
2. Existing deploy scripts can be invoked for production with explicit image references and MDM settings, without adding Terraform-owned runtime commands or secret values.
3. Snowflake native S3 pull deployment or validation confirms integration, stage, pipe, stream, task, procedure, and access readiness.
4. dbt compile/run/test commands for the production target are documented and produce pass/fail evidence.
5. `EDGARTOOLS_GOLD_STATUS`, dynamic table status, and freshness checks are captured as non-secret launch evidence.

**Plans:**

1/2 plans executed

- [x] 02-01-PLAN.md — LIVE-02 AWS deploy readiness, ECR image-promotion runbook, MDM secret-name blockers, and AWS evidence/matrix updates.

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 02-02-PLAN.md — SNOW-01/SNOW-02 guarded Snowflake native-pull smoke, credential-gated dev dbt gate, dbt runbook, and Snowflake evidence/matrix updates.

### Phase 3: MDM Hosted Graph E2E Acceptance

**Goal**: Operators can prove the production MDM and hosted graph path end to end before approving go-live.

**Depends on**: Phase 2

**Requirements**: MDM-01, GRAPH-01, GRAPH-02, LIVE-03

**Success Criteria** (what must be TRUE):

1. Production MDM Snowflake Postgres DSN is loaded from AWS Secrets Manager and connectivity, migration, and counts checks pass without printing the DSN.
2. `edgar-warehouse mdm sync-graph` materializes hosted graph tables for the selected production scope.
3. Strict `edgar-warehouse mdm verify-graph` passes SQL parity and Native App checks, including compute pool availability, `GRAPH_INFO`, `BFS`, and `WCC`.
4. `infra/scripts/run-aws-mdm-e2e.sh` runs with production parameters and reaches migrate, run, backfill, sync, verify, and counts states.
5. `--status-only` and `--skip-preflight` behavior is documented so emergency debug runs cannot be mistaken for Phase 3 or go-live acceptance.

**Plans**: TBD

### Phase 4: Operator Dashboard And Data Issue Triage

**Goal**: Operators can use the dashboard and runbook as the first inspection path for launch data issues.

**Depends on**: Phase 3 and the hosted graph dashboard migration closeout.

**Requirements**: DASH-01, DASH-02, DASH-03

**Success Criteria** (what must be TRUE):

1. Dashboard launches locally with production or production-like read-only configuration and never prints secret values.
2. Dashboard shows MDM entity and relationship counts, hosted graph node and edge counts, mismatch diagnostics, bounded samples, manual refresh, and timestamps.
3. A data issue triage guide maps symptoms to likely layer: ingestion, bronze/silver, MDM, hosted graph, dbt/gold, Native App, dashboard, or permissions.
4. Dashboard UAT records pass/fail notes for launch-critical views without storing credentials, raw exceptions, or unbounded exports.
5. The dashboard remains an inspection surface; CLI verification remains the acceptance gate.

**Plans**: TBD

### Phase 5: Go/No-Go Launch, Evidence, And Handoff

**Goal**: Operators have enough verified evidence and rollback context to make the production launch decision and monitor the first run.

**Depends on**: Phase 4

**Requirements**: OPS-01, OPS-02

**Success Criteria** (what must be TRUE):

1. Go/no-go packet lists every launch gate, owner, command, result, evidence link, and unresolved risk.
2. Stop, rollback, resume, and rerun procedures are documented for AWS Step Functions, Snowflake tasks/dbt, MDM runs, and dashboard verification.
3. Post-launch monitoring checklist covers Step Functions status, CloudWatch logs, Snowflake task history, dbt test failures, MDM counts, hosted graph verification, Native App compute pool health, and dashboard availability.
4. Final approval explicitly states whether launch is go, no-go, or partial with documented blockers.
5. Follow-up work is captured as future requirements or todos rather than silently expanding the launch milestone.

**Plans**: TBD

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Production Readiness Inventory And Launch Gate Contract | v1.5 Go Live | 3/3 | Complete    | 2026-06-14 |
| 2. AWS And Snowflake Production Deployment Dry Run | v1.5 Go Live | 1/2 | In Progress|  |
| 3. MDM Hosted Graph E2E Acceptance | v1.5 Go Live | 0/TBD | Not started | - |
| 4. Operator Dashboard And Data Issue Triage | v1.5 Go Live | 0/TBD | Not started | - |
| 5. Go/No-Go Launch, Evidence, And Handoff | v1.5 Go Live | 0/TBD | Not started | - |
