# Plan Review Questions

## Purpose

Capture the questions that Phase 2 planning and plan-review convergence must
answer before implementation changes move `edgar-warehouse mdm sync-graph` from
external Neo4j to the Snowflake-hosted Neo4j Graph Analytics Native App path.

These questions are source-grounded in the Phase 1 runbook, architecture
decision, graph projection contract, MDM CLI code, Snowflake graph SQL
generator, existing Snowflake access Terraform, and tests.

## Blocking Questions Before Phase 2

1. Is the Snowflake Marketplace listing available in the target dev account and
   region?
2. Has mandatory event sharing been reviewed and accepted by the operator for
   the Native App install?
3. Which Snowflake application name will be used: the default
   `Neo4j_Graph_Analytics` or an account-specific name?
4. Are `CREATE COMPUTE POOL` and `CREATE WAREHOUSE` granted to the application
   before activation?
5. Are `Neo4j_Graph_Analytics.app_user` and
   `Neo4j_Graph_Analytics.app_admin` assignable to the intended consumer roles?
6. Which role and connection context will `edgar-warehouse` use to execute
   graph sync and verification without `NEO4J_*` secrets?
7. Does Phase 2 create `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` as tables,
   views, or compatibility views over the existing `GRAPH_NODES` and
   `GRAPH_EDGES` generated SQL?
8. Will Phase 2 preserve current `tests/mdm/test_snowflake_graph_migration.py`
   assertions, or intentionally update them for new generated file names and
   SQL identifiers?

## Review Questions For Privileges

1. Does the app need only `CREATE COMPUTE POOL` and `CREATE WAREHOUSE`, or are
   additional app privileges required by the live install?
2. Are database role grants scoped to the graph input/output schema instead of
   broad account-level privileges?
3. Do future table and future view grants cover graph input/output objects that
   Phase 2 creates after the Native App is installed?
4. Does the access design align with the existing Terraform pattern in
   `infra/terraform/access/snowflake/modules/account_access/main.tf`, including
   account roles, database usage, schema usage, warehouse usage, all-object
   select grants, and future table/view select grants?
5. Which role receives `app_admin`, and is it limited to operators who need to
   inspect app warehouse or compute-pool state?
6. Which role receives `app_user`, and is that role sufficient for validation
   procedures without granting administration privileges?
7. Where will app-created output tables land, and who can clean them up?
8. Is the app warehouse observable by the operator role that owns production
   runbooks?

## Review Questions For Projection

1. Does the Native App account accept uppercase `NODEID`,
   `SOURCENODEID`, and `TARGETNODEID`, or must Phase 2 expose quoted/camel-case
   `nodeId`, `sourceNodeId`, and `targetNodeId`?
2. If quoted/camel-case identifiers are required, should Phase 2 add views over
   existing `GRAPH_NODES` and `GRAPH_EDGES`, or change the generator output?
3. Should `MDM_GRAPH_NODES` be one multi-label table or a family of label
   specific views derived from it?
4. Should `MDM_GRAPH_EDGES` be one multi-type table or a family of relationship
   specific views derived from it?
5. How are seeded relationship names `IS_INSIDER`, `HOLDS`,
   `COMPANY_HOLDS`, `ISSUED_BY`, `IS_ENTITY_OF`, `HAS_PARENT_COMPANY`,
   `MANAGES_FUND`, and `IS_PERSON_OF` passed to the Native App projection?
6. Does `graph_synced_at` remain the sync watermark, or does Phase 2 introduce a
   Snowflake-specific graph materialization status?
7. Which relationship properties should become top-level columns versus a
   `PROPERTIES`/variant payload?
8. How will the projection avoid placing secrets, raw credentials, EDGAR
   identity values, or internal app secrets in node or edge properties?

## Review Questions For Verification

1. Which query proves node count parity between active MDM entities,
   `MDM_GRAPH_NODES`, and Native App graph projection output?
2. Which query proves relationship parity between active
   `mdm_relationship_instance` rows and `MDM_GRAPH_EDGES` by relationship type?
3. Which bounded diagnostic query reports missing `sourceNodeId` or
   `targetNodeId` endpoint rows?
4. Which Native App procedure provides the first query-level traversal or
   connectivity check without requiring a large graph job?
5. How will the dashboard comparison in Phase 4 read Snowflake-hosted graph
   counts and mismatch diagnostics instead of Bolt counts?
6. How will AWS E2E prove `mdm_sync_graph` and `mdm_verify_graph` without
   `NEO4J_URI`, `NEO4J_USER`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`,
   `NEO4J_DATABASE`, or `NEO4J_SECRET_JSON`?
7. Which tests keep asserting generated SQL file names:
   `00_graph_tables.sql`, `01_validation.sql`, `02_hosted_neo4j_e2e.sql`, and
   `README.md`?
8. Which tests assert Snowflake CLI execution order through `snow sql -c
   <connection> -f <file>`?

## Accepted Risks

- Marketplace availability and compute-pool selector availability are live
  account facts. Phase 1 documents the checks; Phase 2 must not assume success
  without operator evidence.
- The exact identifier casing for `nodeId`, `sourceNodeId`, and `targetNodeId`
  is unresolved until live Native App validation. Phase 2 must preserve or
  deliberately update current SQL tests.
- `edgar-warehouse` still contains external Neo4j CLI and `NEO4J_*` code paths.
  Phase 2 is responsible for changing the command implementation; Phase 1 only
  records the migration contract.
- Existing `GRAPH_NODES` and `GRAPH_EDGES` generated SQL may remain useful as
  compatibility inputs. Renaming them is not required unless the Native App
  contract demands it.

These are planning risks, not implementation shortcuts.

## Phase 2 Entry Gate

Phase 2 must not start until reviewers confirm:

- `01-NATIVE-APP-RUNBOOK.md` has been reviewed for Marketplace, event sharing,
  `CREATE COMPUTE POOL`, `CREATE WAREHOUSE`, app role, compute-pool selector,
  app warehouse, and future table/view grant assumptions.
- `01-ARCHITECTURE-DECISION.md` has been reviewed for the direct cutover from
  external Neo4j to Snowflake-managed graph access.
- `01-GRAPH-PROJECTION-CONTRACT.md` has been reviewed for MDM source-of-truth,
  projection casing, table/view naming, verification mapping, and AWS E2E
  obligations.
- Any live-account item is labeled as documented, validated live, blocked, or
  operator-required before Phase 2 source changes begin.
