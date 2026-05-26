# Snowflake Graph Projection Contract

## Purpose

This contract defines the proposed MDM graph-ready Snowflake inputs for the
Neo4j Graph Analytics Native App. It closes Phase 1 requirement `DISC-04` by
making the node, edge, relationship-type, identifier, property, and validation
expectations explicit before Phase 2 source changes begin.

The contract is proposed, not live-applied. It does not claim that the
Marketplace app, compute pools, graph projection, or algorithm calls have been
run in a Snowflake account. Phase 2 must reconcile the proposed names and
identifier casing with the current repository generator and tests before
changing implementation code.

## Existing MDM Graph Source Of Truth

The MDM relational store remains the source of truth for entities and
relationships. Existing Snowflake source/gold models should be reused where
possible; later phases should add only graph-ready node and edge tables or
views needed by the Native App contract.

Current graph source tables and semantics:

| Source | Fields | Contract use |
| --- | --- | --- |
| `mdm_entity` | `entity_id`, `entity_type`, `is_quarantined`, timestamps | Base active entity universe for graph nodes. Quarantined entities should be excluded from graph-ready inputs. |
| `mdm_entity_type_definition` | `entity_type`, `neo4j_label`, `domain_table`, `primary_id_field`, `is_active` | Label registry for node rows and domain table/property lookup. |
| `mdm_relationship_type` | `rel_type_id`, `rel_type_name`, `source_node_type`, `target_node_type`, `direction`, `is_temporal`, `dedup_key_fields`, `merge_strategy`, `is_active` | Relationship registry for edge type, source/target label expectations, merge semantics, and active relationship types. |
| `mdm_relationship_source_mapping` | `source_system`, `source_table`, source/target fields, `property_mapping`, effective date fields, filters | Source lineage for deriving relationship instances. |
| `mdm_relationship_instance` | `instance_id`, `rel_type_id`, `source_entity_id`, `target_entity_id`, `properties`, `effective_from`, `effective_to`, `source_system`, `source_accession`, `graph_synced_at`, `is_active` | Active edge source rows and parity baseline for Snowflake graph edges. |
| `idx_rel_instance_dedup` | `source_entity_id`, `target_entity_id`, `rel_type_id` | Existing dedupe guard that Phase 2 must preserve or deliberately strengthen when materializing edges. |
| `idx_rel_instance_pending_sync` | `graph_synced_at IS NULL` | Legacy external graph sync pending marker. For the hosted Snowflake path, `graph_synced_at` should become the materialization/projection watermark or be replaced only by an explicit Phase 2 design. |

Seeded relationship types that must be supported:

| Relationship | Source type | Target type | Merge strategy | Notes |
| --- | --- | --- | --- | --- |
| `IS_INSIDER` | `person` | `company` | `extend_temporal` | Officer/director/10 percent owner relationship. |
| `HOLDS` | `person` | `security` | `extend_temporal` | Natural-person security position. |
| `COMPANY_HOLDS` | `company` | `security` | `extend_temporal` | Corporate reporting owner security position. |
| `ISSUED_BY` | `security` | `company` | `extend_temporal` | Security issuer relationship. |
| `IS_ENTITY_OF` | `adviser` | `company` | `replace` | Adviser is the same legal entity as a company. |
| `HAS_PARENT_COMPANY` | `company` | `company` | `replace` | Company parent relationship. |
| `MANAGES_FUND` | `adviser` | `fund` | `extend_temporal` | Adviser manages a private fund. |
| `IS_PERSON_OF` | `adviser` | `person` | `replace` | Individual adviser CIK is the same natural person as an ownership reporting owner. |

## Existing Snowflake Graph Migration Surface

`edgar_warehouse/mdm/snowflake_graph.py` already generates a hosted Snowflake
graph migration surface:

- `00_graph_tables.sql`
- `01_validation.sql`
- `02_hosted_neo4j_e2e.sql`
- `README.md`

The current generated SQL creates `GRAPH_NODES`, `GRAPH_EDGES`,
`GRAPH_NODE_COUNTS`, and `GRAPH_EDGE_COUNTS` under a target schema that defaults
to `NEO4J_GRAPH_MIGRATION`. It reads Snowflake MDM mirror tables directly and
does not require Aura, Bolt, `NEO4J_*` credentials, or JSONL exports.

Current generated shape:

| Current generated object | Current column | Proposed Native App-facing contract | Phase 2 decision |
| --- | --- | --- | --- |
| `GRAPH_NODES` | `NODEID` | `MDM_GRAPH_NODES.nodeId` | Decide whether to quote mixed-case identifiers, expose views with Native App spelling, or deliberately update tests to uppercase-compatible SQL. |
| `GRAPH_NODES` | `LABEL` | `MDM_GRAPH_NODES.label` | Preserve label source from `mdm_entity_type_definition.neo4j_label`. |
| `GRAPH_NODES` | `PROPERTIES` | `MDM_GRAPH_NODES.properties` | Keep property payload non-secret and review keys before projection. |
| `GRAPH_EDGES` | `EDGEID` | `MDM_GRAPH_EDGES.edgeId` | Use `mdm_relationship_instance.instance_id` as stable edge id. |
| `GRAPH_EDGES` | `RELATIONSHIP_TYPE` | `MDM_GRAPH_EDGES.relationshipType` | Use `mdm_relationship_type.rel_type_name`. |
| `GRAPH_EDGES` | `SOURCENODEID` | `MDM_GRAPH_EDGES.sourceNodeId` | Required Native App spelling is `sourceNodeId`. |
| `GRAPH_EDGES` | `TARGETNODEID` | `MDM_GRAPH_EDGES.targetNodeId` | Required Native App spelling is `targetNodeId`. |
| `GRAPH_EDGES` | `PROPERTIES` | `MDM_GRAPH_EDGES.properties` | Include source, temporal, and relationship payload fields. |

`tests/mdm/test_snowflake_graph_migration.py` currently asserts generated file
names, `GRAPH_NODES`, `GRAPH_EDGES`, MDM source table references, validation
SQL, and Snowflake CLI execution order. Phase 2 must either preserve those tests
by layering Native App-facing views on top of existing generated tables, or
deliberately update the tests with the chosen `MDM_GRAPH_NODES` and
`MDM_GRAPH_EDGES` contract.

## Proposed Snowflake Schema

Proposed schema:

```text
EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH
```

Proposed Native App-facing inputs:

```text
EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_NODES
EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_EDGES
```

These can be physical tables, views over existing generated `GRAPH_NODES` and
`GRAPH_EDGES`, or a hybrid. Phase 2 should prefer the smallest change that:

1. Preserves MDM as the source of truth.
2. Reuses current Snowflake source/gold and MDM mirror data.
3. Exposes the Native App required column names `nodeId`, `sourceNodeId`, and
   `targetNodeId`.
4. Keeps graph inputs idempotent across repeated `edgar-warehouse mdm
   sync-graph` runs.
5. Avoids putting secrets, credentials, or raw sensitive values into graph
   property payloads.

## Node Input Contract

`MDM_GRAPH_NODES` exposes one row per active, non-quarantined MDM entity that
should be visible to graph analytics.

Required Native App column:

| Column | Source | Semantics |
| --- | --- | --- |
| `nodeId` | `mdm_entity.entity_id` | Stable graph node id. Must match `MDM_GRAPH_EDGES.sourceNodeId` and `MDM_GRAPH_EDGES.targetNodeId`. |

Recommended columns:

| Column | Source | Semantics |
| --- | --- | --- |
| `label` | `mdm_entity_type_definition.neo4j_label` | Human-readable node label such as `Company`, `Adviser`, `Person`, `Security`, or `Fund`. |
| `entityType` | `mdm_entity.entity_type` | Registry key such as `company`, `adviser`, `person`, `security`, or `fund`. |
| `domainTable` | `mdm_entity_type_definition.domain_table` | Domain table used to enrich node properties. |
| `primaryIdField` | `mdm_entity_type_definition.primary_id_field` | Domain-specific identifier field used for operator inspection. |
| `properties` | Domain rows plus entity metadata | Snowflake object containing non-secret business attributes such as CIK, CRD number, canonical name, ticker, issuer id, adviser id, fund type, and timestamps. |
| `sourceSystem` | MDM/source priority context where available | Optional provenance field for dashboard filtering and diagnostics. |
| `syncedAt` | Phase 2 materialization timestamp | Timestamp for graph-ready row creation or refresh. Proposed until Phase 2 selects the exact watermark model. |

Node property payloads must be reviewed before production. They should not
include Snowflake passwords, private keys, OAuth tokens, EDGAR identity values,
raw secret JSON, or app logs.

## Relationship Input Contract

`MDM_GRAPH_EDGES` exposes one row per active MDM relationship instance whose
relationship type is active.

Required Native App columns:

| Column | Source | Semantics |
| --- | --- | --- |
| `sourceNodeId` | `mdm_relationship_instance.source_entity_id` | Stable source node id. |
| `targetNodeId` | `mdm_relationship_instance.target_entity_id` | Stable target node id. |

Recommended columns:

| Column | Source | Semantics |
| --- | --- | --- |
| `edgeId` | `mdm_relationship_instance.instance_id` | Stable relationship row id. |
| `relationshipType` | `mdm_relationship_type.rel_type_name` | Relationship type such as `MANAGES_FUND` or `ISSUED_BY`. |
| `sourceNodeType` | `mdm_relationship_type.source_node_type` | Expected source entity type for parity validation. |
| `targetNodeType` | `mdm_relationship_type.target_node_type` | Expected target entity type for parity validation. |
| `mergeStrategy` | `mdm_relationship_type.merge_strategy` | Existing MDM merge behavior: `extend_temporal`, `always_insert`, or `replace`. |
| `properties` | `mdm_relationship_instance.properties` plus source/temporal fields | Relationship property payload. |
| `effectiveFrom` | `mdm_relationship_instance.effective_from` | Temporal start where available. |
| `effectiveTo` | `mdm_relationship_instance.effective_to` | Temporal end where available. |
| `sourceSystem` | `mdm_relationship_instance.source_system` | Source lineage such as `ownership_filing`, `adv_filing`, `derived`, or `mdm_backfill`. |
| `sourceAccession` | `mdm_relationship_instance.source_accession` | Filing accession or business source id where available. |
| `graphSyncedAt` | `mdm_relationship_instance.graph_synced_at` | Legacy graph sync watermark. Phase 2 must decide whether Snowflake materialization updates it or a new Snowflake-specific watermark is needed. |
| `isActive` | `mdm_relationship_instance.is_active` | Active-state filter. The graph projection should include only active rows by default. |

The contract intentionally maps current MDM fields instead of redesigning the
gold layer. Relationship parity in Phase 3 should compare active
`mdm_relationship_instance` rows by `rel_type_name` against `MDM_GRAPH_EDGES`
rows by `relationshipType`.

## Native App Projection Example

The following example is illustrative and has not been run live for this
project. It shows the intended shape for a bounded Native App smoke test once
Phase 2 materializes `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`.

```sql
CALL Neo4j_Graph_Analytics.graph.wcc('CPU_X64_XS', {
  'project': {
    'defaultTablePrefix': 'EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH',
    'nodeTables': ['MDM_GRAPH_NODES'],
    'relationshipTables': {
      'MDM_GRAPH_EDGES': {
        'sourceTable': 'MDM_GRAPH_NODES',
        'targetTable': 'MDM_GRAPH_NODES',
        'orientation': 'NATURAL'
      }
    }
  },
  'compute': { 'consecutiveIds': true },
  'write': [{
    'nodeLabel': 'MDM_GRAPH_NODES',
    'outputTable': 'EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_WCC_SMOKE'
  }]
});
```

Live-account validation must confirm the Marketplace listing, event sharing,
app role grants, `CREATE COMPUTE POOL`, `CREATE WAREHOUSE`, database role grants
to the application, compute selector availability, and output table write
permissions before treating this as production-ready.

## Verification Mapping

Later phases must prove the hosted Snowflake graph path with these checks:

| Obligation | Proposed proof |
| --- | --- |
| Node count | Compare active, non-quarantined MDM entities by entity type to `MDM_GRAPH_NODES` by `entityType` or `label`. |
| Edge parity | Compare active `mdm_relationship_instance` rows joined to `mdm_relationship_type` against `MDM_GRAPH_EDGES` by `relationshipType`, `sourceNodeId`, `targetNodeId`, `edgeId`, source fields, and temporal fields. |
| Relationship endpoint integrity | Verify every `sourceNodeId` and `targetNodeId` resolves to a `nodeId`. |
| Traversal/connectivity check | Run at least one Native App procedure or query-level connectivity check relevant to ownership, adviser, company, security, or fund relationships. |
| Dashboard comparison | Phase 4 dashboard reads Snowflake-hosted graph diagnostics and shows bounded mismatch filters without mutating MDM or graph state. |
| AWS E2E | Phase 3 AWS MDM E2E reaches graph sync and hosted graph verification without `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, or `NEO4J_SECRET_JSON`. |

## Ownership And Cleanup

`edgar-warehouse mdm sync-graph` remains the command surface for materializing
graph-ready Snowflake node and edge state. The dashboard remains read-only.

Snowflake ownership model:

- Data inputs should live in a governed graph schema such as
  `EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH`.
- The Neo4j Native App receives only the database role grants required to read
  graph inputs and create approved output tables.
- `EDGARTOOLS_GRAPH_APP_USER` can inspect result tables.
- `EDGARTOOLS_GRAPH_APP_ADMIN` is reserved for app warehouse and compute-pool
  operations.
- App-created algorithm outputs must have a clear cleanup policy before
  production validation writes long-lived tables.

## Phase 2 Handoff

Phase 2 should implement or update the Snowflake graph sync contract with these
decisions made explicitly:

1. Whether to materialize physical `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES`
   tables, views over existing `GRAPH_NODES` and `GRAPH_EDGES`, or both.
2. Whether to preserve current uppercase unquoted identifiers (`NODEID`,
   `SOURCENODEID`, `TARGETNODEID`) and use compatibility views, or use quoted
   mixed-case identifiers matching `nodeId`, `sourceNodeId`, and `targetNodeId`.
3. Whether `tests/mdm/test_snowflake_graph_migration.py` continues to assert
   current generated file names and SQL identifiers, or is updated to the new
   contract.
4. How `graph_synced_at` maps to hosted Snowflake materialization now that the
   milestone no longer uses an external Bolt sync as the graph target.
5. How bounded execution by entity type, relationship type, row limit, and
   operator repair workflow is preserved.
6. How Snowflake connection context is obtained without external `NEO4J_*`
   milestone validation secrets.

## Sources

- `.planning/workstreams/neo4j-snowflake/PROJECT.md`
- `.planning/workstreams/neo4j-snowflake/REQUIREMENTS.md`
- `.planning/workstreams/neo4j-snowflake/ROADMAP.md`
- `.planning/workstreams/neo4j-snowflake/STATE.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-CONTEXT.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-RESEARCH.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-PATTERNS.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md`
- `edgar_warehouse/mdm/migrations/runtime.py`
- `edgar_warehouse/mdm/migrations/002_seed_data.sql`
- `edgar_warehouse/mdm/graph.py`
- `edgar_warehouse/mdm/snowflake_graph.py`
- `tests/mdm/test_graph.py`
- `tests/mdm/test_snowflake_graph_migration.py`
