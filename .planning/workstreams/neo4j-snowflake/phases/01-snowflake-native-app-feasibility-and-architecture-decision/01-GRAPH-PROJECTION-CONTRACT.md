# Graph Projection Contract

## Purpose

Define the Phase 2 contract for materializing EdgarTools MDM graph state into
Snowflake graph-ready node and edge inputs for the Neo4j Graph Analytics Native
App.

This is a planning contract only. It does not claim that the Native App has been
run live. Phase 2 must either preserve the current generated SQL tests or update
them deliberately when implementing the table/view shape.

## Existing MDM Graph Source Of Truth

The MDM relational store remains the source of truth for entities and
relationships.

Entity registry:

| Source | Key fields | Contract use |
| --- | --- | --- |
| `mdm_entity_type_definition` | `entity_type`, `neo4j_label`, `domain_table`, `primary_id_field`, `is_active` | Maps MDM entity types to graph labels and domain tables. |
| `mdm_entity` | `entity_id`, `entity_type`, `is_quarantined` | Supplies stable node identity and active node eligibility. |
| Domain tables | `mdm_company`, `mdm_adviser`, `mdm_person`, `mdm_security`, `mdm_fund` | Supply label-specific graph properties. |

Relationship registry:

| Source | Key fields | Contract use |
| --- | --- | --- |
| `mdm_relationship_type` | `rel_type_id`, `rel_type_name`, `source_node_type`, `target_node_type`, `direction`, `is_temporal`, `dedup_key_fields`, `merge_strategy`, `is_active` | Defines relationship type names, allowed source/target node classes, direction, temporal semantics, and active relationship types. |
| `mdm_relationship_instance` | `instance_id`, `rel_type_id`, `source_entity_id`, `target_entity_id`, `properties`, `effective_from`, `effective_to`, `source_system`, `source_accession`, `graph_synced_at`, `is_active` | Supplies graph edge identity, endpoints, properties, provenance, active status, and sync status. |
| `idx_rel_instance_dedup` | `source_entity_id`, `target_entity_id`, `rel_type_id` | Preserves idempotent edge identity expectations for Phase 2 sync. |
| `idx_rel_instance_pending_sync` | `graph_synced_at` where pending | Supports bounded pending-sync selection before the Snowflake-hosted path replaces Bolt stamping. |

Seeded relationship types to preserve:

- `IS_INSIDER`: `person` -> `company`
- `HOLDS`: `person` -> `security`
- `COMPANY_HOLDS`: `company` -> `security`
- `ISSUED_BY`: `security` -> `company`
- `IS_ENTITY_OF`: `adviser` -> `company`
- `HAS_PARENT_COMPANY`: `company` -> `company`
- `MANAGES_FUND`: `adviser` -> `fund`
- `IS_PERSON_OF`: `adviser` -> `person`

Current `GraphSyncEngine` behavior to preserve in Snowflake form:

- Nodes are keyed by `entity_id`.
- Relationship rows are selected from active `mdm_relationship_instance` rows.
- `source_entity_id` and `target_entity_id` are the graph endpoints.
- `properties`, `effective_from`, `effective_to`, and `source_accession` are
  relationship properties.
- `graph_synced_at IS NULL` currently means pending external graph sync. Phase 2
  must decide whether this timestamp is retained as the Snowflake graph
  materialization watermark or replaced by a Snowflake-specific status field.

## Existing Snowflake Graph Migration Surface

`edgar_warehouse/mdm/snowflake_graph.py` already generates hosted graph SQL:

- `00_graph_tables.sql`
- `01_validation.sql`
- `02_hosted_neo4j_e2e.sql`
- `README.md`

The current generated graph tables are:

| Current artifact | Current columns | Notes |
| --- | --- | --- |
| `GRAPH_NODES` | `NODEID`, `LABEL`, `PROPERTIES` | Union of company, adviser, person, security, and fund domain tables. |
| `GRAPH_EDGES` | `EDGEID`, `RELATIONSHIP_TYPE`, `SOURCENODEID`, `TARGETNODEID`, `PROPERTIES` | Active `MDM_RELATIONSHIP_INSTANCE` joined to `MDM_RELATIONSHIP_TYPE`. |
| `GRAPH_NODE_COUNTS` | `LABEL`, `NODE_COUNT` | Validation view. |
| `GRAPH_EDGE_COUNTS` | `RELATIONSHIP_TYPE`, `EDGE_COUNT` | Validation view. |

Current tests in `tests/mdm/test_snowflake_graph_migration.py` assert that the
generator writes `GRAPH_NODES`, `GRAPH_EDGES`, `MDM_RELATIONSHIP_INSTANCE`,
`GRAPH_NODE_COMPANY_PAGERANK`, and the deterministic SQL file names above.

## Proposed Snowflake Schema

Phase 2 should expose Native App-facing graph inputs in a governed graph schema,
for example:

```text
EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_NODES
EDGARTOOLS_<ENV>.EDGARTOOLS_GRAPH.MDM_GRAPH_EDGES
```

The implementation may choose physical tables, views over existing generated
tables, or a hybrid. It must reuse existing source/gold and MDM graph models
where possible and avoid redesigning the gold layer.

Reconciliation required before implementation:

| Contract concept | Existing SQL shape | Native App-facing spelling | Phase 2 decision |
| --- | --- | --- | --- |
| Node id | `GRAPH_NODES.NODEID` | `nodeId` | Either create quoted/camel-case views or confirm the app accepts uppercase identifiers. |
| Source node id | `GRAPH_EDGES.SOURCENODEID` | `sourceNodeId` | Same casing decision as node id. |
| Target node id | `GRAPH_EDGES.TARGETNODEID` | `targetNodeId` | Same casing decision as node id. |
| Relationship type | `GRAPH_EDGES.RELATIONSHIP_TYPE` | Relationship table or property name | Preserve seeded type values and app projection mapping. |
| Edge id | `GRAPH_EDGES.EDGEID` | Edge property or id column | Preserve `instance_id` traceability. |
| Properties | `GRAPH_NODES.PROPERTIES`, `GRAPH_EDGES.PROPERTIES` | Property columns or object payload | Avoid secrets and keep provenance fields queryable. |

Phase 2 must either keep current generated names and add compatibility
views, or rename generated artifacts and update
`tests/mdm/test_snowflake_graph_migration.py` intentionally.

## Node Input Contract

`MDM_GRAPH_NODES` must contain one row per active, non-quarantined MDM entity
eligible for graph projection.

Required columns:

| Column | Source | Notes |
| --- | --- | --- |
| `nodeId` | `mdm_entity.entity_id` | Stable graph node key. |
| `label` | `mdm_entity_type_definition.neo4j_label` | Values include `Company`, `Adviser`, `Person`, `Security`, `Fund`. |
| `entity_type` | `mdm_entity.entity_type` | Lowercase MDM type for parity checks. |
| `properties` | Domain table fields | Object payload, with no credentials or secrets. |
| `source_updated_at` | domain-specific timestamp if available | Optional freshness support. |

Recommended property fields:

- `entity_id`
- `cik`, `owner_cik`, or `crd_number` when available
- `canonical_name` or `canonical_title`
- `ticker`, `primary_ticker`, `primary_exchange`
- `issuer_entity_id`, `adviser_entity_id`, `parent_company_entity_id`
- `security_type`, `fund_type`, `primary_role`

## Relationship Input Contract

`MDM_GRAPH_EDGES` must contain one row per active MDM relationship instance
eligible for graph projection.

Required columns:

| Column | Source | Notes |
| --- | --- | --- |
| `edgeId` | `mdm_relationship_instance.instance_id` | Stable edge traceability key. |
| `relationshipType` | `mdm_relationship_type.rel_type_name` | Seeded values listed in this contract. |
| `sourceNodeId` | `mdm_relationship_instance.source_entity_id` | Must match `MDM_GRAPH_NODES.nodeId`. |
| `targetNodeId` | `mdm_relationship_instance.target_entity_id` | Must match `MDM_GRAPH_NODES.nodeId`. |
| `properties` | `mdm_relationship_instance.properties` plus provenance fields | Include `source_system`, `source_accession`, temporal fields, and `instance_id`. |
| `is_active` | `mdm_relationship_instance.is_active` | Projection filters to true. |
| `graph_synced_at` | `mdm_relationship_instance.graph_synced_at` | Preserve pending-sync visibility or document replacement. |

Relationship property payload should include:

- `instance_id`
- `source_system`
- `source_accession`
- `effective_from`
- `effective_to`
- `properties`
- `merge_strategy` from `mdm_relationship_type`
- `source_node_type` and `target_node_type` for diagnostics

## Native App Projection Example

Illustrative Native App call shape for Phase 2 validation. This has not been
run live and must be validated against the installed app and account region.

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

If the app requires distinct node tables per label or relationship tables per
type, Phase 2 should generate views from `MDM_GRAPH_NODES` and
`MDM_GRAPH_EDGES` rather than changing MDM relationship semantics.

## Verification Mapping

| Requirement | Required proof |
| --- | --- |
| Node count parity | Count active MDM entities by type, count `MDM_GRAPH_NODES` by label, and compare with Native App projection result metadata when available. |
| Edge parity | Count active `mdm_relationship_instance` rows by `rel_type_name` and compare with `MDM_GRAPH_EDGES` by `relationshipType`. |
| Missing endpoint diagnostics | Left join `MDM_GRAPH_EDGES` to `MDM_GRAPH_NODES` on `sourceNodeId` and `targetNodeId`; bounded sample of missing endpoints. |
| Traversal/connectivity check | Run at least one Native App graph algorithm or traversal-equivalent query that proves important ownership/adviser/fund connectivity is reachable. |
| Dashboard comparison | Phase 4 dashboard reads Snowflake-hosted graph counts and mismatch diagnostics, not external Bolt counts. |
| AWS E2E | Phase 3 AWS run reaches graph sync and hosted verification without `NEO4J_URI`, `NEO4J_PASSWORD`, or `NEO4J_SECRET_JSON`. |

## Ownership And Cleanup

- Graph input schema ownership remains with Snowflake platform/operator roles.
- The Native App receives only required database role grants to input and output
  schemas.
- Algorithm output tables land in governed graph output schemas.
- Consumer roles receive read access to output tables without ownership by
  default.
- Cleanup policy for algorithm output tables must be documented before
  production rollout.

## Phase 2 Handoff

Phase 2 must:

1. Decide whether `MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` are physical tables,
   views, or compatibility views over existing `GRAPH_NODES` and `GRAPH_EDGES`.
2. Resolve identifier casing for `nodeId`, `sourceNodeId`, and `targetNodeId`
   and update tests deliberately if the current uppercase SQL shape changes.
3. Preserve seeded relationship type names and source/target semantics.
4. Preserve idempotency and pending-sync visibility from `graph_synced_at` or
   document the replacement Snowflake status model.
5. Keep `edgar-warehouse mdm sync-graph` as the operator command surface.
6. Avoid external Neo4j credential requirements for milestone verification.

## Sources

- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-RESEARCH.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-ARCHITECTURE-DECISION.md`
- `.planning/workstreams/neo4j-snowflake/phases/01-snowflake-native-app-feasibility-and-architecture-decision/01-NATIVE-APP-RUNBOOK.md`
- `edgar_warehouse/mdm/migrations/runtime.py`
- `edgar_warehouse/mdm/migrations/002_seed_data.sql`
- `edgar_warehouse/mdm/graph.py`
- `edgar_warehouse/mdm/snowflake_graph.py`
- `tests/mdm/test_graph.py`
- `tests/mdm/test_snowflake_graph_migration.py`
