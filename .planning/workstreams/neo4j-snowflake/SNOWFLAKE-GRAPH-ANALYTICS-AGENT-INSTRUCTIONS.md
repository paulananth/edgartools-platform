# Neo4j Graph Analytics On Snowflake - Agent Instructions

source: operator-supplied
captured: 2026-05-26
workstream: neo4j-snowflake

---

## Purpose

Use this document as the live Snowflake graph analytics context for Phase 2 and later
`neo4j-snowflake` planning. It records the currently available graph data, Native App
algorithm surface, compute pools, app details, and permission assumptions for the
Snowflake-hosted Neo4j Graph Analytics path.

Do not treat this document as source-code truth. Confirm live-account state when a plan or
implementation depends on current row counts, grants, app version, or algorithm availability.

## Graph Data Location

- Database: `EDGARTOOLS_DEV`
- Schema: `NEO4J_GRAPH_MIGRATION`

## Node Tables

Node table prefix: `GRAPH_NODE_`

| Table | Rows | Key Columns |
| --- | ---: | --- |
| `GRAPH_NODE_COMPANY` | 367 | `NODEID`, `CIK`, `COMPANY_KEY`, `SIC_CODE` |
| `GRAPH_NODE_PERSON` | 159 | `NODEID`, `OWNER_CIK`, `AFFILIATED_COMPANY_COUNT` |
| `GRAPH_NODE_TICKER` | 525 | `NODEID` |
| `GRAPH_NODE_SECURITY` | 46 | `NODEID` |
| `GRAPH_NODE_FILING` | 89 | `NODEID`, `FILING_KEY`, `CIK`, `COMPANY_KEY`, `FORM_KEY`, `DATE_KEY`, `SIZE` |

## Edge Tables

Edge table prefix: `GRAPH_EDGE_`

| Table | Rows | Key Columns |
| --- | ---: | --- |
| `GRAPH_EDGE_COMPANY_FILED` | 286455 | `SOURCENODEID`, `TARGETNODEID` |
| `GRAPH_EDGE_COMPANY_HAS_TICKER` | 525 | `SOURCENODEID`, `TARGETNODEID` |
| `GRAPH_EDGE_HOLDS` | 64 | `SOURCENODEID`, `TARGETNODEID`, `SHARES_OWNED` |
| `GRAPH_EDGE_ISSUED_BY` | 46 | `SOURCENODEID`, `TARGETNODEID` |
| `GRAPH_EDGE_IS_INSIDER` | 37 | `SOURCENODEID`, `TARGETNODEID` |
| `GRAPH_EDGE_PERSON_EVIDENCED_BY_FILING` | 93 | `SOURCENODEID`, `TARGETNODEID` |

## Algorithm Results Already Computed

| Table | Algorithm | Owner |
| --- | --- | --- |
| `GRAPH_NODE_*_PAGERANK` (5 tables) | PageRank | `NEO4J_GRAPH_ANALYTICS` |
| `GRAPH_NODE_*_COMMUNITY` (5 tables) | Community Detection (Louvain) | `NEO4J_GRAPH_ANALYTICS` |
| `GRAPH_SHORTEST_PATH_RESULTS` | Shortest Path | `NEO4J_GRAPH_ANALYTICS` |

## Available Algorithms

Algorithm procedures are available through `NEO4J_GRAPH_ANALYTICS.GRAPH.*`.

| Category | Procedures |
| --- | --- |
| Centrality | `PAGE_RANK`, `ARTICLE_RANK`, `BETWEENNESS`, `DEGREE` |
| Community | `LOUVAIN`, `LEIDEN`, `LABEL_PROPAGATION`, `WCC`, `TRIANGLE_COUNT` |
| Path Finding | `DIJKSTRA`, `DIJKSTRA_SINGLE_SOURCE`, `DELTA_STEPPING`, `BFS`, `YENS`, `FASTPATH` |
| Similarity | `NODE_SIMILARITY`, `NODE_SIMILARITY_FILTERED`, `KNN`, `KNN_FILTERED` |
| Embeddings | `FAST_RP`, `NODE2VEC`, `HASHGNN` |
| ML | `GS_NC_TRAIN`, `GS_NC_PREDICT`, `GS_UNSUP_TRAIN`, `GS_UNSUP_PREDICT`, `KMEANS` |
| Flow | `MAX_FLOW`, `MAX_FLOW_MIN_COST` |
| Utility | `GRAPH_INFO`, `JOB_LOG`, `SHOW_MODELS`, `SHOW_AVAILABLE_COMPUTE_POOLS` |
| Agent | `CREATE_AGENT`, `DROP_AGENT` |

## Available Compute Pools

- `CPU_X64_XS`
- `CPU_X64_M`
- `CPU_X64_L`
- `GPU_NV_S`
- `HIGHMEM_X64_S`
- `HIGHMEM_X64_M`
- `HIGHMEM_X64_L`

## Algorithm Call Pattern

```sql
SELECT *
FROM TABLE(
  NEO4J_GRAPH_ANALYTICS.GRAPH.<ALGORITHM>(
    'EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION',
    {
      'project_name': 'my_graph',
      'compute_pool': 'CPU_X64_XS',
      'node_tables': ['GRAPH_NODE_COMPANY', 'GRAPH_NODE_PERSON'],
      'relationship_tables': ['GRAPH_EDGE_IS_INSIDER'],
      'write_options': {'output_prefix': 'MY_RESULT'}
    }
  )
);
```

## Rich Node And Edge Data

These tables contain names or details useful for lookups and joins.

| Table | Names Or Details |
| --- | --- |
| `NEO4J_NODE_COMPANY` | `CANONICAL_NAME`, `PRIMARY_TICKER`, `PRIMARY_EXCHANGE`, `SIC_DESCRIPTION`, `STATE_OF_INCORPORATION`, `CIK`, `EIN`, `FISCAL_YEAR_END` |
| `NEO4J_NODE_PERSON` | `CANONICAL_NAME`, `PRIMARY_ROLE`, `ROLE_TITLES`, `OWNER_CIK`, `AFFILIATED_COMPANY_COUNT` |
| `NEO4J_NODE_SECURITY` | `NEO4J_ELEMENT_ID`, `ENTITY_ID` |
| `NEO4J_EDGE_HOLDS` | `AS_OF_DATE`, `SHARES_OWNED`, `DIRECT_INDIRECT`, `EFFECTIVE_FROM` |
| `NEO4J_EDGE_IS_INSIDER` | `INSIDER_ROLE`, `TITLE`, `EFFECTIVE_FROM` |

## Graph Schema

Relationship shape:

- `PERSON` -> `COMPANY` via `IS_INSIDER` (37)
- `COMPANY` -> `FILING` via `FILED` (286455)
- `COMPANY` -> `TICKER` via `HAS_TICKER` (525)
- `PERSON` -> `SECURITY` via `HOLDS` (64)
- `SECURITY` -> `COMPANY` via `ISSUED_BY` (46)
- `PERSON` -> `FILING` via `EVIDENCED_BY` (93)

## Grants And Permissions

| Privilege | Scope |
| --- | --- |
| `CREATE COMPUTE POOL` | Account |
| `CREATE WAREHOUSE` | Account |
| `USAGE` | `EDGARTOOLS_DEV.NEO4J_GRAPH_ANALYTICS_MIGRATION_ROLE` |
| `CREATE TABLE` | `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION` |

## App Details

| Property | Value |
| --- | --- |
| App Name | `NEO4J_GRAPH_ANALYTICS` |
| Type | Native App (Marketplace) |
| Version | `V1_0`, Patch 31 |
| Owner | `ACCOUNTADMIN` |
| Installed | 2026-05-25 |

## Planning Implications

- Phase 2 should treat `EDGARTOOLS_DEV.NEO4J_GRAPH_MIGRATION` as the current live graph
  schema for implementation planning and validation examples.
- Phase 2 should reconcile existing Phase 1 contract names such as `MDM_GRAPH_NODES` and
  `MDM_GRAPH_EDGES` with the live Native App table prefix convention `GRAPH_NODE_*` and
  `GRAPH_EDGE_*`.
- Verification plans can use existing PageRank, Louvain community, and shortest-path result
  tables as sanity checks, but should not assume they prove MDM parity by themselves.
- Plans that execute algorithms should default to `CPU_X64_XS` unless the dataset or
  algorithm explicitly requires a larger pool.
- Live-account validation must confirm grants and role boundaries before encoding them into
  operator-facing commands.
