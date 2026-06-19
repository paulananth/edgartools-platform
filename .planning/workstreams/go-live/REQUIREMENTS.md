# Requirements: v1.6 Production Launch Execution

workstream: go-live
status: planned
milestone: v1.6 Production Launch Execution
defined: 2026-06-19

---

## Core Value

Launch the AWS-first EdgarTools Platform into production with repeatable operator gates
that prove SEC ingestion, Snowflake native pull, dbt gold, MDM, hosted graph verification,
and dashboard inspection are ready without adding non-AWS architecture or unsafe secret
handling.

## Milestone Requirements

### Launch Execution

- [ ] **LIVE-04**: Operator can apply prod AWS passive infrastructure and capture required Terraform outputs as non-secret evidence.
- [ ] **LIVE-05**: Operator can deploy active AWS application components with explicit image references and produce `infra/aws-prod-application.json` summary evidence without committing sensitive generated JSON.
- [ ] **LIVE-06**: Release owner can flip the go/no-go decision only after every v1.6 blocker has PASS evidence and owner sign-off.

### Snowflake Native Pull And Gold

- [ ] **SNOW-03**: Snowflake operator can deploy the prod native-pull stack, including storage integration, stage, source mirror tables, pipe, stream, procedures, task, and access reconciliation.
- [ ] **SNOW-04**: Snowflake operator can run `dbt run --target prod` and `dbt test --target prod`, then capture non-secret `EDGARTOOLS_GOLD_STATUS` and freshness evidence.

### MDM And Hosted Graph

- [ ] **MDM-02**: MDM operator can populate prod `postgres_dsn` and `snowflake` secrets, then verify connectivity, migration, and counts without printing secret values.
- [ ] **GRAPH-03**: MDM operator can run bounded prod `mdm sync-graph` and strict prod `mdm verify-graph` with SQL parity, Native App, compute pool, `GRAPH_INFO`, `BFS`, and `WCC` evidence.
- [ ] **GRAPH-04**: Operator can run prod AWS MDM E2E through `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts`.

### Dashboard And Data Issue Review

- [ ] **DASH-04**: Dashboard reviewer can run production or production-like read-only UAT for all 5 launch-critical views and record pass/fail notes.

### Operations And Security

- [ ] **OPS-03**: Operators can execute the production launch sequence in documented order with required approvals, bounded stop conditions, and rollback/resume notes.
- [ ] **SEC-02**: v1.6 evidence remains secret-safe: no DSNs, tokens, passwords, Terraform state, raw connector traces, raw Native App logs, or sensitive generated JSON are committed.
- [ ] **ISO-03**: v1.6 stays AWS/Snowflake-focused and does not add non-AWS deployment paths, registries, storage targets, workflow engines, or secret-management systems.

## Future Requirements

- Managed dashboard deployment after local/operator production dashboard launch is proven.
- Historical trend views for data quality, graph parity, and launch gate outcomes.
- Production cost dashboards for Snowflake Native App compute pools and AWS Step Functions runs.
- Formal deprecation or removal of external Neo4j runtime remnants after production hosted graph validation is stable.

## Out Of Scope

| Feature | Reason |
|---------|--------|
| Non-AWS deployment path | Violates locked project architecture. |
| Terraform-owned runtime commands or secret values | Terraform is passive infrastructure only in this repo. |
| Dashboard write controls | The dashboard is an inspection surface, not an operator action console. |
| Public or customer-facing dashboard launch | This milestone is production operator launch execution, not external product launch. |
| Full architecture redesign | v1.6 should execute the existing AWS/Snowflake/MDM launch sequence, not replace it. |
| Unbounded production backfill expansion | Launch gates should remain bounded and explicit before larger operational runs. |

## Traceability

Which phases cover which requirements.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LIVE-04 | Phase 6 | Pending |
| LIVE-05 | Phase 6 | Pending |
| SNOW-03 | Phase 7 | Pending |
| SNOW-04 | Phase 7 | Pending |
| MDM-02 | Phase 8 | Pending |
| GRAPH-03 | Phase 9 | Pending |
| GRAPH-04 | Phase 9 | Pending |
| DASH-04 | Phase 10 | Pending |
| LIVE-06 | Phase 11 | Pending |
| OPS-03 | Phase 11 | Pending |
| SEC-02 | Phase 11 | Pending |
| ISO-03 | Phase 11 | Pending |

**Coverage:**

- v1.6 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0

---

*Requirements defined: 2026-06-19*
*Last updated: 2026-06-19 after v1.6 roadmap creation*
