# Phase 1 Plan Review Questions

## Purpose

This checklist captures the questions that must be reviewed before Phase 2
implementation changes begin. It is intended for plan-review convergence after
the Native App runbook, architecture decision, and graph projection contract are
read together.

The checklist keeps uncertainty explicit. It does not authorize implementation
shortcuts, broad grants, external Neo4j fallback validation, or source changes
before the Phase 2 plan answers the blocking items.

## Blocking Questions Before Phase 2

1. Is the Neo4j Graph Analytics Native App Marketplace listing available in the
   Snowflake account and region targeted for dev validation?
2. Has an operator accepted mandatory event sharing for the Native App after
   reviewing the app telemetry event definitions?
3. Which Snowflake role will install and activate the app, and does that role
   have authority to grant `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`
   application privileges?
4. What exact application name will Phase 2 assume: the documented default
   `Neo4j_Graph_Analytics`, or an account-specific application name?
5. Which account roles will receive the app role grants for
   `Neo4j_Graph_Analytics.app_user` and `Neo4j_Graph_Analytics.app_admin`?
6. Which Snowflake connection context will `edgar-warehouse` use for hosted
   graph materialization and validation: account, user or service principal,
   role, database, schema, warehouse, and app warehouse?
7. How will `edgar-warehouse` obtain that Snowflake execution context without
   relying on external `NEO4J_*` secrets or `NEO4J_SECRET_JSON`?
8. Does Phase 2 keep the current generated `GRAPH_NODES` and `GRAPH_EDGES` SQL
   artifacts and add Native App-facing compatibility views, or rename the
   generated artifacts to `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`?
9. Should `tests/mdm/test_snowflake_graph_migration.py` keep asserting current
   generated file names and uppercase SQL identifiers, or be deliberately
   updated to the final graph projection contract?
10. What is the accepted `graph_synced_at` meaning after the graph target moves
    from external Bolt sync to Snowflake-hosted graph materialization?

## Review Questions For Privileges

1. Can the app be activated with only the required application privileges
   `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`, without copying broad example
   grants such as `ALL PRIVILEGES`?
2. What database role will be granted to the application for graph input access,
   and will it be limited to database usage, graph schema usage, table/view
   select, future table select, future view select, and approved output table
   creation?
3. Does the existing Snowflake access Terraform pattern in
   `infra/terraform/access/snowflake/modules/account_access/main.tf` need a new
   graph schema grant surface, or can Phase 2 defer Terraform and document a
   manual operator grant for the first validation?
4. How will future table and future view grants be represented so graph input
   refreshes do not break app access?
5. Which role can inspect app-created output tables without receiving ownership
   or drop privileges by default?
6. What cleanup owner is responsible for algorithm output tables such as
   `MDM_GRAPH_WCC_SMOKE`?
7. How will app warehouse observability be handled for
   `Neo4j_Graph_Analytics_app_warehouse`, and which role may operate or monitor
   the app warehouse?
8. Which compute-pool selector is available in the live account? Is
   `CPU_X64_XS` available, or must Phase 2 parameterize a different selector?
9. What failure signal should distinguish missing app role assignment from
   missing data grants, missing future table grants, and missing output table
   creation privileges?

## Review Questions For Projection

1. Will the Native App-facing objects be physical tables, views over existing
   generated tables, or a hybrid?
2. Will the contract use quoted mixed-case identifiers `nodeId`,
   `sourceNodeId`, and `targetNodeId`, or unquoted uppercase Snowflake
   identifiers with compatibility verified against the Native App?
3. If compatibility views are used, should they be named `MDM_GRAPH_NODES` and
   `MDM_GRAPH_EDGES` while preserving existing `GRAPH_NODES` and `GRAPH_EDGES`
   as implementation details?
4. How will the projection exclude quarantined entities and inactive
   relationships while preserving active MDM relationship parity?
5. Which domain properties are safe to include in node and edge `properties`
   payloads, and which fields must be excluded to avoid secrets or overly broad
   disclosure?
6. How will `mdm_relationship_type.rel_type_name`,
   `source_node_type`, `target_node_type`, and `merge_strategy` be carried into
   graph edge diagnostics?
7. Should `mdm_relationship_instance.instance_id` become `edgeId`, or should
   Phase 2 derive a deterministic edge id from source, target, type, temporal
   bounds, accession, and properties?
8. How will the existing `idx_rel_instance_dedup` semantics be reflected in the
   Snowflake graph-ready edge materialization so repeated sync runs remain
   stable?
9. What migration path updates `edgar-warehouse mdm sync-graph` without
   changing its operator-facing command name or bounded options such as
   relationship type, row limit, and per-type limit?
10. What generated SQL file names should Phase 2 produce, and which tests will
    prove those names are stable?

## Review Questions For Verification

1. What exact SQL proves node counts match active, non-quarantined MDM entities
   by entity type and graph label?
2. What exact SQL proves edge parity between active
   `mdm_relationship_instance` rows and `MDM_GRAPH_EDGES` by relationship type,
   source node id, target node id, edge id, source accession, and temporal
   fields?
3. What query proves every edge endpoint resolves to an existing graph node?
4. Which Native App traversal or connectivity check is the first required
   smoke test for ownership, adviser, company, security, or fund reachability?
5. Will the first live check use `graph.wcc`, another low-cost algorithm, or a
   query-level Native App diagnostic?
6. Which output schema and table naming convention will host algorithm results,
   and how will cleanup be verified?
7. How will `edgar-warehouse mdm verify-graph` distinguish app permission
   failures, missing projection inputs, missing algorithm output tables, and
   true MDM parity defects?
8. What dashboard comparison data should Phase 4 consume from the hosted graph
   path without mutating MDM or graph state?
9. How will the AWS MDM E2E script prove graph sync and hosted graph
   verification without `NEO4J_*` or `NEO4J_SECRET_JSON`?
10. What log redaction rule prevents Snowflake credentials, app telemetry, or
    graph property payloads from being copied into planning docs or build logs?

## Accepted Risks

- Marketplace availability, mandatory event sharing, compute-pool selector
  availability, and final application role grant behavior remain live-account
  validation risks after Phase 1.
- The exact casing and quoted-identifier strategy for `nodeId`,
  `sourceNodeId`, and `targetNodeId` is unresolved until Phase 2 chooses and
  tests the implementation path.
- The current repository already has a hosted Snowflake graph SQL generator,
  but it may need compatibility views or deliberate test updates before it
  satisfies the Native App-facing `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`
  contract.
- `graph_synced_at` currently means pending or completed external graph sync;
  its hosted Snowflake meaning must be made explicit before implementation.
- These risks are planning uncertainties only. They are not permission to skip
  node count proof, edge parity proof, traversal/connectivity proof, dashboard
  comparison, AWS E2E validation, least-privilege grants, or secret hygiene.

## Phase 2 Entry Gate

Phase 2 must not start until the following artifacts have been reviewed together
and any changes from review are either applied or explicitly deferred:

1. `01-NATIVE-APP-RUNBOOK.md`
2. `01-ARCHITECTURE-DECISION.md`
3. `01-GRAPH-PROJECTION-CONTRACT.md`
4. This `01-PLAN-REVIEW-QUESTIONS.md`

The Phase 2 plan must answer the blocking questions that affect source changes:
projection object names, identifier casing, Snowflake execution context, app and
database role grant model, `graph_synced_at` semantics, generated SQL test
expectations, and the first hosted graph verification path.
