"""Snowflake SQL generation for hosted Neo4j graph analytics tables."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Any


DEFAULT_TARGET_SCHEMA = "NEO4J_GRAPH_MIGRATION"
DEFAULT_MDM_SCHEMA = "MDM"


@dataclass(frozen=True)
class SnowflakeGraphMigrationConfig:
    env: str
    output_dir: Path
    target_database: str | None = None
    target_schema: str = DEFAULT_TARGET_SCHEMA
    mdm_database: str | None = None
    mdm_schema: str = DEFAULT_MDM_SCHEMA
    silver_path: Path | None = None

    def resolved_target_database(self) -> str:
        return self.target_database or f"EDGARTOOLS_{self.env.upper()}"

    def resolved_mdm_database(self) -> str:
        return self.mdm_database or self.resolved_target_database()


def generate_snowflake_graph_migration(config: SnowflakeGraphMigrationConfig) -> dict[str, Path]:
    """Write SQL files that build graph-ready tables inside Snowflake.

    Neo4j Graph Analytics is treated as Snowflake-hosted. The generated SQL
    reads Snowflake MDM mirror tables directly; it does not require Aura,
    Bolt, `NEO4J_*` credentials, or JSONL exports from an external graph.
    """
    context = {
        "target_database": _ident(config.resolved_target_database()),
        "target_schema": _ident(config.target_schema),
        "mdm_database": _ident(config.resolved_mdm_database()),
        "mdm_schema": _ident(config.mdm_schema),
        "silver_path": config.silver_path,
    }

    files = {
        "00_graph_tables.sql": render_graph_tables(context),
        "01_validation.sql": render_validation(context),
        "02_hosted_neo4j_e2e.sql": render_hosted_neo4j_e2e(context),
        "README.md": render_readme(context),
    }
    config.output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in files.items():
        path = config.output_dir / name
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        written[name] = path
    return written


def run_snowflake_graph_sql(files: dict[str, Path], *, snow_connection: str) -> list[str]:
    """Execute generated SQL files with Snowflake CLI in deterministic order."""
    executed: list[str] = []
    for name in sorted(files):
        if not name.endswith(".sql"):
            continue
        path = files[name]
        subprocess.run(
            ["snow", "sql", "-c", snow_connection, "-f", str(path)],
            check=True,
        )
        executed.append(name)
    return executed


def run_hosted_neo4j_e2e(files: dict[str, Path], *, snow_connection: str) -> list[str]:
    """Execute only the read-only hosted Neo4j Graph Analytics e2e SQL."""
    path = files["02_hosted_neo4j_e2e.sql"]
    subprocess.run(
        ["snow", "sql", "-c", snow_connection, "-f", str(path)],
        check=True,
    )
    return ["02_hosted_neo4j_e2e.sql"]


def render_graph_tables(context: dict[str, Any]) -> str:
    return f"""-- Build graph-ready node and edge tables for Snowflake-hosted Neo4j Graph Analytics.
-- Neo4j is not external in this flow. Source data comes from Snowflake MDM mirror tables.

CREATE SCHEMA IF NOT EXISTS {context["target_database"]}.{context["target_schema"]};

CREATE OR REPLACE TABLE {_fq(context, "MDM_GRAPH_NODES")} AS
SELECT
  E.ENTITY_ID::STRING AS NODEID,
  ETD.NEO4J_LABEL::STRING AS LABEL,
  E.ENTITY_TYPE::STRING AS ENTITY_TYPE,
  'mdm' AS SOURCE_SYSTEM,
  COALESCE(
    C.VALID_FROM,
    A.VALID_FROM,
    P.VALID_FROM,
    S.VALID_FROM,
    F.VALID_FROM,
    E.UPDATED_AT
  ) AS SOURCE_UPDATED_AT,
  E.CREATED_AT AS CREATED_AT,
  E.UPDATED_AT AS UPDATED_AT,
  OBJECT_CONSTRUCT_KEEP_NULL(
    'entity_id', E.ENTITY_ID,
    'entity_type', E.ENTITY_TYPE,
    'label', ETD.NEO4J_LABEL,
    'cik', COALESCE(C.CIK, A.CIK),
    'owner_cik', P.OWNER_CIK,
    'crd_number', A.CRD_NUMBER,
    'canonical_name', COALESCE(C.CANONICAL_NAME, A.CANONICAL_NAME, P.CANONICAL_NAME, F.CANONICAL_NAME),
    'canonical_title', S.CANONICAL_TITLE,
    'ticker', COALESCE(C.TICKER, C.PRIMARY_TICKER),
    'primary_ticker', C.PRIMARY_TICKER,
    'primary_exchange', C.PRIMARY_EXCHANGE,
    'issuer_entity_id', S.ISSUER_ENTITY_ID,
    'adviser_entity_id', F.ADVISER_ENTITY_ID,
    'parent_company_entity_id', C.PARENT_COMPANY_ENTITY_ID,
    'security_type', S.SECURITY_TYPE,
    'fund_type', F.FUND_TYPE,
    'primary_role', P.PRIMARY_ROLE
  ) AS PROPERTIES
FROM {_mdm_fq(context, "MDM_ENTITY")} E
JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
LEFT JOIN {_mdm_fq(context, "MDM_COMPANY")} C
  ON C.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'company'
LEFT JOIN {_mdm_fq(context, "MDM_ADVISER")} A
  ON A.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'adviser'
LEFT JOIN {_mdm_fq(context, "MDM_PERSON")} P
  ON P.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'person'
LEFT JOIN {_mdm_fq(context, "MDM_SECURITY")} S
  ON S.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'security'
LEFT JOIN {_mdm_fq(context, "MDM_FUND")} F
  ON F.ENTITY_ID = E.ENTITY_ID
 AND E.ENTITY_TYPE = 'fund'
WHERE E.IS_QUARANTINED = FALSE;

CREATE OR REPLACE TABLE {_fq(context, "MDM_GRAPH_EDGES")} AS
SELECT
  RI.INSTANCE_ID::STRING AS EDGEID,
  RT.REL_TYPE_NAME::STRING AS RELATIONSHIP_TYPE,
  RI.SOURCE_ENTITY_ID::STRING AS SOURCENODEID,
  RI.TARGET_ENTITY_ID::STRING AS TARGETNODEID,
  RT.SOURCE_NODE_TYPE::STRING AS SOURCE_ENTITY_TYPE,
  RT.TARGET_NODE_TYPE::STRING AS TARGET_ENTITY_TYPE,
  RI.SOURCE_SYSTEM::STRING AS SOURCE_SYSTEM,
  RI.SOURCE_ACCESSION::STRING AS SOURCE_ACCESSION,
  RI.EFFECTIVE_FROM AS EFFECTIVE_FROM,
  RI.EFFECTIVE_TO AS EFFECTIVE_TO,
  RT.MERGE_STRATEGY::STRING AS MERGE_STRATEGY,
  CASE
    WHEN RI.GRAPH_SYNCED_AT IS NULL THEN 'PENDING'
    ELSE 'SYNCED'
  END AS GRAPH_SYNC_STATUS,
  RI.GRAPH_SYNCED_AT AS GRAPH_SYNCED_AT,
  RI.CREATED_AT AS CREATED_AT,
  RI.UPDATED_AT AS UPDATED_AT,
  OBJECT_CONSTRUCT_KEEP_NULL(
    'instance_id', RI.INSTANCE_ID,
    'source_system', RI.SOURCE_SYSTEM,
    'source_accession', RI.SOURCE_ACCESSION,
    'effective_from', RI.EFFECTIVE_FROM,
    'effective_to', RI.EFFECTIVE_TO,
    'properties', TRY_PARSE_JSON(RI.PROPERTIES),
    'merge_strategy', RT.MERGE_STRATEGY,
    'source_node_type', RT.SOURCE_NODE_TYPE,
    'target_node_type', RT.TARGET_NODE_TYPE,
    'graph_sync_status', CASE
      WHEN RI.GRAPH_SYNCED_AT IS NULL THEN 'PENDING'
      ELSE 'SYNCED'
    END
  ) AS PROPERTIES
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
  ON RT.REL_TYPE_ID = RI.REL_TYPE_ID
WHERE RI.IS_ACTIVE = TRUE
  AND RT.IS_ACTIVE = TRUE;

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODES")} AS
SELECT NODEID, LABEL, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGES")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")};

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_COMPANY")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'company';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_PERSON")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'person';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_SECURITY")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'security';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_ADVISER")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'adviser';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_FUND")} AS
SELECT NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_NODES")}
WHERE ENTITY_TYPE = 'fund';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_INSIDER")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_INSIDER';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'HOLDS';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_COMPANY_HOLDS")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'COMPANY_HOLDS';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_ISSUED_BY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'ISSUED_BY';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_ENTITY_OF")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_ENTITY_OF';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_HAS_PARENT_COMPANY")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'HAS_PARENT_COMPANY';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_MANAGES_FUND")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'MANAGES_FUND';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_IS_PERSON_OF")} AS
SELECT EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_ENTITY_TYPE, TARGET_ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_ACCESSION, EFFECTIVE_FROM, EFFECTIVE_TO, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, CREATED_AT, UPDATED_AT, PROPERTIES
FROM {_fq(context, "MDM_GRAPH_EDGES")}
WHERE RELATIONSHIP_TYPE = 'IS_PERSON_OF';

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_NODE_COUNTS")} AS
SELECT LABEL, COUNT(*) AS NODE_COUNT
FROM {_fq(context, "MDM_GRAPH_NODES")}
GROUP BY LABEL;

CREATE OR REPLACE VIEW {_fq(context, "GRAPH_EDGE_COUNTS")} AS
SELECT RELATIONSHIP_TYPE, COUNT(*) AS EDGE_COUNT
FROM {_fq(context, "MDM_GRAPH_EDGES")}
GROUP BY RELATIONSHIP_TYPE;
"""


def render_validation(context: dict[str, Any]) -> str:
    return f"""-- Validation for Snowflake-hosted Neo4j Graph Analytics tables.

SELECT 'snowflake_graph_nodes' AS METRIC, COUNT(*) AS VALUE
FROM {_fq(context, "MDM_GRAPH_NODES")}
UNION ALL
SELECT 'snowflake_graph_edges' AS METRIC, COUNT(*) AS VALUE
FROM {_fq(context, "MDM_GRAPH_EDGES")}
UNION ALL
SELECT 'active_mdm_entities' AS METRIC, COUNT(*) AS VALUE
FROM {_mdm_fq(context, "MDM_ENTITY")} E
JOIN {_mdm_fq(context, "MDM_ENTITY_TYPE_DEFINITION")} ETD
  ON ETD.ENTITY_TYPE = E.ENTITY_TYPE
 AND ETD.IS_ACTIVE = TRUE
WHERE E.IS_QUARANTINED = FALSE
UNION ALL
SELECT 'mdm_relationship_instances_active' AS METRIC, COUNT(*) AS VALUE
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")}
WHERE IS_ACTIVE = TRUE;

SELECT LABEL, NODE_COUNT
FROM {_fq(context, "GRAPH_NODE_COUNTS")}
ORDER BY LABEL;

SELECT RELATIONSHIP_TYPE, EDGE_COUNT
FROM {_fq(context, "GRAPH_EDGE_COUNTS")}
ORDER BY RELATIONSHIP_TYPE;

SELECT
  'active_mdm_relationship_parity' AS CHECK_NAME,
  RT.REL_TYPE_NAME AS RELATIONSHIP_TYPE,
  COUNT(RI.INSTANCE_ID) AS MDM_ACTIVE_COUNT,
  COALESCE(G.EDGE_COUNT, 0) AS SNOWFLAKE_GRAPH_EDGE_COUNT,
  COUNT(RI.INSTANCE_ID) - COALESCE(G.EDGE_COUNT, 0) AS MDM_MINUS_GRAPH
FROM {_mdm_fq(context, "MDM_RELATIONSHIP_TYPE")} RT
LEFT JOIN {_mdm_fq(context, "MDM_RELATIONSHIP_INSTANCE")} RI
  ON RI.REL_TYPE_ID = RT.REL_TYPE_ID
 AND RI.IS_ACTIVE = TRUE
LEFT JOIN {_fq(context, "GRAPH_EDGE_COUNTS")} G
  ON G.RELATIONSHIP_TYPE = RT.REL_TYPE_NAME
WHERE RT.IS_ACTIVE = TRUE
GROUP BY RT.REL_TYPE_NAME, G.EDGE_COUNT
ORDER BY RT.REL_TYPE_NAME;

SELECT
  'missing_graph_edge_endpoints' AS CHECK_NAME,
  E.RELATIONSHIP_TYPE,
  E.SOURCENODEID,
  E.TARGETNODEID,
  E.EDGEID,
  IFF(S.NODEID IS NULL, TRUE, FALSE) AS MISSING_SOURCE_NODE,
  IFF(T.NODEID IS NULL, TRUE, FALSE) AS MISSING_TARGET_NODE
FROM {_fq(context, "MDM_GRAPH_EDGES")} E
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} S
  ON S.NODEID = E.SOURCENODEID
LEFT JOIN {_fq(context, "MDM_GRAPH_NODES")} T
  ON T.NODEID = E.TARGETNODEID
WHERE S.NODEID IS NULL OR T.NODEID IS NULL
LIMIT 100;
"""


def render_hosted_neo4j_e2e(context: dict[str, Any]) -> str:
    return f"""-- Read-only e2e validation for Neo4j Graph Analytics hosted in Snowflake.
-- This checks existing Snowflake graph tables and Neo4j Graph Analytics result tables.

SELECT 'GRAPH_NODE_COMPANY' AS TABLE_NAME, COUNT(*) AS ROW_COUNT
FROM {_fq(context, "GRAPH_NODE_COMPANY")}
UNION ALL
SELECT 'GRAPH_NODE_PERSON', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_PERSON")}
UNION ALL
SELECT 'GRAPH_NODE_SECURITY', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_SECURITY")}
UNION ALL
SELECT 'GRAPH_EDGE_HOLDS', COUNT(*)
FROM {_fq(context, "GRAPH_EDGE_HOLDS")}
UNION ALL
SELECT 'GRAPH_EDGE_ISSUED_BY', COUNT(*)
FROM {_fq(context, "GRAPH_EDGE_ISSUED_BY")}
UNION ALL
SELECT 'GRAPH_EDGE_IS_INSIDER', COUNT(*)
FROM {_fq(context, "GRAPH_EDGE_IS_INSIDER")}
UNION ALL
SELECT 'GRAPH_NODE_COMPANY_PAGERANK', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_COMPANY_PAGERANK")}
UNION ALL
SELECT 'GRAPH_NODE_COMPANY_COMMUNITY', COUNT(*)
FROM {_fq(context, "GRAPH_NODE_COMPANY_COMMUNITY")}
UNION ALL
SELECT 'GRAPH_SHORTEST_PATH_RESULTS', COUNT(*)
FROM {_fq(context, "GRAPH_SHORTEST_PATH_RESULTS")};
"""


def render_readme(context: dict[str, Any]) -> str:
    return f"""# Snowflake-Hosted Neo4j Graph Analytics

This generated runbook builds graph-ready node and edge tables inside Snowflake.
Neo4j is not an external Aura or Bolt runtime in this flow; all graph analytics
data is hosted in Snowflake and sourced from the Snowflake MDM mirror tables.

Run order:

1. `snow sql -c <connection> -f 00_graph_tables.sql`
2. `snow sql -c <connection> -f 01_validation.sql`
3. `snow sql -c <connection> -f 02_hosted_neo4j_e2e.sql`

Target schema: `{context["target_database"]}.{context["target_schema"]}`
MDM source schema: `{context["mdm_database"]}.{context["mdm_schema"]}`
Silver source: `{context["silver_path"] or "environment-backed"}`

The generated tables use Neo4j Graph Analytics friendly columns:

- `MDM_GRAPH_NODES(NODEID, LABEL, ENTITY_TYPE, SOURCE_SYSTEM, SOURCE_UPDATED_AT, CREATED_AT, UPDATED_AT, PROPERTIES)`
- `MDM_GRAPH_EDGES(EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, SOURCE_SYSTEM, SOURCE_ACCESSION, GRAPH_SYNC_STATUS, GRAPH_SYNCED_AT, PROPERTIES)`
- `GRAPH_NODE_*` views expose one Native App-compatible node table per label.
- `GRAPH_EDGE_*` views expose one Native App-compatible relationship table per type.

`MDM_GRAPH_NODES` and `MDM_GRAPH_EDGES` are the canonical contract tables.
`GRAPH_NODES` and `GRAPH_EDGES` remain compatibility views over the canonical
tables for older validation queries.

Neo4j Graph Analytics procedures such as `NEO4J_GRAPH_ANALYTICS.GRAPH.PAGE_RANK`,
`NEO4J_GRAPH_ANALYTICS.GRAPH.LOUVAIN`, and
`NEO4J_GRAPH_ANALYTICS.GRAPH.GRAPH_INFO` consume these generated graph tables.
This SQL generation step does not invoke those procedures. Algorithm output
tables should land in governed `{context["target_database"]}.{context["target_schema"]}`
tables with operator cleanup ownership.

For an already materialized Snowflake-hosted graph, run only
`02_hosted_neo4j_e2e.sql`. It validates existing graph node/edge tables and
Neo4j Graph Analytics result tables without mutating Snowflake.
"""


def _fq(context: dict[str, Any], name: str) -> str:
    return f"{context['target_database']}.{context['target_schema']}.{_ident(name)}"


def _mdm_fq(context: dict[str, Any], name: str) -> str:
    return f"{context['mdm_database']}.{context['mdm_schema']}.{_ident(name)}"


def _ident(value: str) -> str:
    cleaned = str(value).upper()
    if not cleaned.replace("_", "").isalnum() or not cleaned[0].isalpha():
        raise ValueError(f"Unsafe Snowflake identifier: {value!r}")
    return cleaned
