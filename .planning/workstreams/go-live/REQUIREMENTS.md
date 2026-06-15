# Requirements: Go Live

workstream: go-live
status: active
milestone: v1.5 Go Live
updated: 2026-06-13

---

## Milestone Requirements

### Launch Gate And Cutover

- [x] **LIVE-01**: Operator can run a documented production preflight that verifies required AWS passive infrastructure outputs, application deployment artifacts, Snowflake connections, and secret containers without printing secret values.
- [x] **LIVE-02**: Operator can deploy or update active AWS application components through existing deploy scripts with explicit image references, MDM enabled when required, and no Terraform-owned runtime commands or secret values.
- [ ] **LIVE-03**: Operator can run bounded production status and E2E checks, distinguish known blockers from launch failures, and stop before expensive AWS execution when local acceptance gates cannot pass.

### Snowflake Native Pull And Gold

- [x] **SNOW-01**: Operator can deploy or validate the Snowflake native S3 pull stack for production, including storage integration, stage, source mirror tables, pipe, stream, procedures, tasks, and access grants.
- [x] **SNOW-02**: Operator can run dbt compile/run/test for the production target and capture non-secret `EDGARTOOLS_GOLD_STATUS` and dynamic table freshness evidence.

### MDM And Hosted Graph

- [ ] **MDM-01**: Production MDM Snowflake Postgres configuration is populated through AWS Secrets Manager, and MDM connectivity, migration, and counts checks pass with secret-safe output.
- [ ] **GRAPH-01**: `edgar-warehouse mdm sync-graph` and strict `edgar-warehouse mdm verify-graph` pass in the target environment with SQL parity, Native App grants, compute pool availability, `GRAPH_INFO`, `BFS`, and `WCC` proof.
- [ ] **GRAPH-02**: AWS MDM E2E reaches `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts` through the Snowflake-hosted graph path without requiring external `NEO4J_*` credentials.

### Dashboard And Data Issue Review

- [ ] **DASH-01**: Operator can launch the read-only dashboard against the target environment configuration and inspect MDM overview, hosted graph overview, mismatch diagnostics, manual refresh timestamps, and bounded samples.
- [ ] **DASH-02**: Operator has a one-stop data issue workflow that classifies ingestion, bronze/silver, MDM, hosted graph, dbt/gold, Native App, and dashboard issues with owners and remediation paths.
- [ ] **DASH-03**: Dashboard documentation and UAT evidence avoid secrets, raw connector exceptions, stack traces, mutation controls, and unbounded exports.

### Operations And Security

- [ ] **OPS-01**: Go/no-go runbook lists launch commands, expected pass criteria, rollback or stop procedures, resume steps, required approvals, and evidence capture rules.
- [ ] **OPS-02**: Post-launch monitoring and incident checklist covers Step Functions status, CloudWatch logs, Snowflake task/dbt failures, Native App compute pool health, dashboard availability, and escalation paths.
- [x] **SEC-01**: Evidence bundle is secret-scrubbed, IAM and Snowflake grants are reviewed for launch scope, and no DSNs, tokens, passwords, Terraform state, or sensitive generated deployment values are committed.

### Isolation

- [x] **ISO-01**: Work stays isolated under `.planning/workstreams/go-live/` and reviewed launch docs unless a phase explicitly scopes source-code or runbook changes.
- [x] **ISO-02**: The milestone preserves the locked AWS-only architecture and does not introduce non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management systems.

## Future Requirements

- [ ] Managed dashboard deployment after local/operator dashboard launch is proven.
- [ ] Historical trend views for data quality, graph parity, and launch gate outcomes.
- [ ] Production cost dashboards for Snowflake Native App compute pools and AWS Step Functions runs.
- [ ] Removal or formal deprecation of external Neo4j runtime remnants after production hosted graph validation is stable.

## Out Of Scope

| Feature | Reason |
|---------|--------|
| Non-AWS deployment path | Violates locked project architecture. |
| Terraform-owned runtime commands or secret values | Terraform is passive infrastructure only in this repo. |
| Dashboard write controls | The dashboard is an inspection surface, not an operator action console. |
| Public or customer-facing dashboard launch | This milestone is production operator readiness, not external product launch. |
| Full architecture redesign | Go-live should harden and validate existing AWS/Snowflake/MDM surfaces. |
| Unbounded production backfill expansion | Launch gates should start bounded and explicit before larger operational runs. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIVE-01 | Phase 1 | Complete |
| SEC-01 | Phase 1 | Complete |
| ISO-01 | Phase 1 | Complete |
| ISO-02 | Phase 1 | Complete |
| LIVE-02 | Phase 2 | Complete |
| SNOW-01 | Phase 2 | Complete |
| SNOW-02 | Phase 2 | Complete |
| MDM-01 | Phase 3 | Pending |
| GRAPH-01 | Phase 3 | Pending |
| GRAPH-02 | Phase 3 | Pending |
| LIVE-03 | Phase 3 | Pending |
| DASH-01 | Phase 4 | Pending |
| DASH-02 | Phase 4 | Pending |
| DASH-03 | Phase 4 | Pending |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |

**Coverage:**

- v1.5 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0

---

*Requirements defined: 2026-06-13*
*Last updated: 2026-06-13 after milestone initialization*
