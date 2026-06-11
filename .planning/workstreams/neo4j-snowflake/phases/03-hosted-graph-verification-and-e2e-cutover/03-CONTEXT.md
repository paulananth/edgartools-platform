# Phase 3: Hosted Graph Verification And E2E Cutover - Context

**Gathered:** 2026-06-11T10:47:00Z
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 proves the Snowflake-hosted Neo4j Graph Analytics Native App path end to end. The phase moves `edgar-warehouse mdm verify-graph` from a basic Snowflake table-count check into a strict hosted graph verification gate, validates Native App graph execution, automates least-privilege app grants where safe, and updates AWS MDM E2E validation so success no longer depends on external Neo4j connectivity.

This phase does not migrate the review dashboard. Dashboard-hosted graph comparison remains Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Verification Depth
- **D-01:** `edgar-warehouse mdm verify-graph` must be a strict Phase 3 parity gate, not a basic node and edge count check.
- **D-02:** A missing or failing Snowflake Native App check must fail `verify-graph`.
- **D-03:** `verify-graph` must require exact parity between active MDM rows and Snowflake graph rows. Any node or relationship mismatch fails the gate.
- **D-04:** Failure output must include structured diagnostics grouped by node class and relationship type, with small samples of missing or extra IDs so operators can repair the underlying data.

### Native App Smoke Test
- **D-05:** Native App proof must include `GRAPH_INFO` metadata visibility and real algorithm execution against the ownership/adviser/fund graph.
- **D-06:** Both `BFS` and `WCC` are required for Phase 3 algorithm proof. `BFS` should use a deterministic known node from the synced graph where possible; `WCC` proves graph-wide algorithm execution.
- **D-07:** `verify-graph` should auto-create missing Native App prerequisites when the operation is safe and appropriately scoped. Anything that cannot be safely created automatically must fail with explicit remediation instructions.
- **D-08:** Native App proof runs by default inside `verify-graph`. Opt-out is allowed only for local/offline test contexts and must not satisfy live Phase 3 acceptance.

### Snowflake App Grants
- **D-09:** Phase 3 should define a dedicated database role for `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION` access and grant that role to the Snowflake Native App, rather than relying on `ACCOUNTADMIN` ownership.
- **D-10:** Grant setup should be repo-managed automation, such as Snowflake SQL and an operator runbook, not manual-only account setup.
- **D-11:** Grants must be least-privilege and read-only for graph verification: database usage, schema usage, graph table/view select access, required application-role grants, and required compute prerequisites only.
- **D-12:** `verify-graph` must validate database roles, table grants, app role grants, and compute prerequisites. Missing items fail with exact remediation output.

### AWS E2E Cutover
- **D-13:** AWS MDM E2E success should replace external Neo4j connectivity with Snowflake `sync-graph` plus strict hosted `verify-graph`.
- **D-14:** Lingering `NEO4J_*` task-definition or script references are warnings only for Phase 3, unless they are still used as a functional success gate or block the Snowflake-hosted path.
- **D-15:** Phase 3 E2E proof must include Step Functions execution validation, not only local script execution.
- **D-16:** Final Phase 3 acceptance requires a documented live dev run using `SNOW_CONNECTION=snowconn`, `DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV`, and the AWS dev deployment, with non-secret outputs captured.

### the agent's Discretion
No implementation areas were delegated fully to the agent. The planner can choose concrete helper boundaries and SQL/procedure packaging, provided the decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Workstream Control
- `.planning/workstreams/neo4j-snowflake/PROJECT.md` - Workstream project definition.
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md` - Pending Phase 3 requirements are `SYNC-04`, `SNOW-03`, `VERIFY-01`, `VERIFY-02`, `VERIFY-03`, and `VERIFY-05`; `VERIFY-04` remains Phase 4.
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md` - Phase 3 goal and success criteria for hosted verification and AWS E2E cutover.
- `.planning/workstreams/neo4j-snowflake/STATE.md` - Current state at 50%, Phase 2 complete and Phase 3 ready to plan.

### Prior Architecture And Contracts
- `.planning/workstreams/neo4j-snowflake/SNOWFLAKE-GRAPH-ANALYTICS-AGENT-INSTRUCTIONS.md` - Operator-supplied Native App notes and live-account expectations.
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md` - Accepted decision that Snowflake Marketplace Neo4j Graph Analytics replaces the external Neo4j target for this milestone.
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md` - Native App install, app role, warehouse, compute-pool, and operator setup guidance.
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-GRAPH-PROJECTION-CONTRACT.md` - Node and edge projection contract for Native App graph inputs.
- `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-01-SUMMARY.md` - Graph projection SQL contract implementation summary.
- `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-02-SUMMARY.md` - Reusable Snowflake graph sync executor summary.
- `.planning/workstreams/neo4j-snowflake/phases/02-snowflake-graph-sync-contract/02-03-SUMMARY.md` - `sync-graph` CLI wiring summary and Phase 3 handoff.

### Code Surfaces
- `edgar_warehouse/mdm/cli.py` - CLI handlers for `sync-graph`, `verify-graph`, `load-relationships`, and secret-safe JSON output.
- `edgar_warehouse/mdm/snowflake_graph.py` - Snowflake graph table generation, allowed entity/relationship filters, target schema defaults, and sync executor.
- `tests/mdm/test_cli_snowflake_graph.py` - Credential-free CLI tests for Snowflake graph sync and current minimal `verify-graph` behavior.
- `tests/mdm/test_snowflake_graph_migration.py` - SQL generation and Snowflake graph migration tests.
- `tests/mdm/test_export.py` - Snowflake connection and secret-safe error behavior tests.
- `infra/scripts/run-aws-mdm-e2e.sh` - AWS MDM E2E and Step Functions validation script that currently still names the chain MDM/Neo4j and starts `mdm_check_connectivity`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `SnowflakeGraphSyncExecutor.from_env()` already shares the Snowflake connection settings used by MDM export paths and returns target database/schema, table names, applied filters, and node/edge counts.
- `DEFAULT_TARGET_SCHEMA` is `NEO4J_GRAPH_MIGRATION`; Phase 3 should keep that as the default Native App graph schema unless the operator supplies an override.
- Existing CLI tests monkeypatch executor/session boundaries and clear `NEO4J_*` env vars, which is the right pattern for credential-free Phase 3 tests.

### Established Patterns
- CLI handlers catch `RuntimeError` and `ValueError`, print a command-prefixed stderr message, emit secret-safe JSON on success, and return nonzero for failed gates.
- Graph sync filters already fail closed for unknown entity and relationship types before Snowflake cursor execution.
- `load-relationships` remains derivation-only by default; graph materialization is explicit via `--graph-sync`.

### Integration Points
- `edgar_warehouse/mdm/cli.py` currently implements `verify-graph` as `COUNT(*)` against `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`; Phase 3 should replace this with strict SQL parity, grant validation, Native App smoke tests, and structured diagnostics.
- `edgar_warehouse/mdm/snowflake_graph.py` should likely host reusable SQL/procedure helpers for grant validation, graph parity queries, and Native App smoke-test SQL so CLI code stays narrow.
- `infra/scripts/run-aws-mdm-e2e.sh` currently starts `mdm_check_connectivity`, `mdm_migrate`, `mdm_run`, `mdm_backfill_relationships`, `mdm_sync_graph`, `mdm_verify_graph`, and `mdm_counts`. Phase 3 should make the graph success path Snowflake-hosted and keep Step Functions validation.

</code_context>

<specifics>
## Specific Ideas

Live investigation before discussion found a dev Snowflake account with `NEO4J_GRAPH_ANALYTICS` installed, graph tables present in `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION`, and the current minimal `verify-graph` succeeding when run with `SNOWFLAKE_CONNECTION=snowconn` and `DBT_SNOWFLAKE_DATABASE=EDGARTOOLS_DEV`. It also found no grants to the application, no database roles in `EDGARTOOLS_DEV`, and no available Native App compute pools. Treat those as Phase 3 setup and validation targets, not as secrets.

For the final documented live run, capture non-secret command outputs such as node/edge counts, relationship parity by type, Native App smoke-test status, Step Functions execution ARN/status, and remediation messages for any intentionally missing prerequisites.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 3 scope.

</deferred>

---

*Phase: 3-Hosted Graph Verification And E2E Cutover*
*Context gathered: 2026-06-11T10:47:00Z*
