# Snowflake-Hosted Neo4j Graph Analytics

Neo4j graph analytics for this platform is hosted in Snowflake. Do not treat
Neo4j as an external Aura or Bolt runtime for the supported analytics path, and
do not add operator guidance that depends on `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, or external Neo4j secret containers.

The active operator flow is:

```text
bronze -> silver -> MDM entities/relationships -> Snowflake MDM mirror
  -> Snowflake graph-ready node/edge tables
  -> Neo4j Graph Analytics in Snowflake
```

## Generate And Apply

Use the Snowflake CLI connection already configured for the environment:

```bash
python scripts/ops/neo4j-snowflake-migration.py \
  --env dev \
  --snow-connection edgartools-dev \
  --output-dir .tmp/neo4j-snowflake-graph \
  --apply
```

For production:

```bash
python scripts/ops/neo4j-snowflake-migration.py \
  --env prod \
  --snow-connection edgartools-prod \
  --output-dir .tmp/neo4j-snowflake-graph-prod \
  --apply
```

The script generates and optionally runs:

- `00_graph_tables.sql`: creates `GRAPH_NODES`, `GRAPH_EDGES`, and count views.
- `01_validation.sql`: compares Snowflake graph edge counts to active MDM relationship rows.
- `02_hosted_neo4j_e2e.sql`: read-only e2e validation for existing Snowflake-hosted graph and algorithm result tables.
- `README.md`: records the target database/schema and run order.

When graph tables already exist in Snowflake, run only the hosted e2e check:

```bash
python scripts/ops/neo4j-snowflake-migration.py \
  --env dev \
  --snow-connection edgartools-dev \
  --output-dir .tmp/neo4j-snowflake-graph \
  --hosted-e2e
```

The graph tables use Neo4j Graph Analytics friendly columns:

```text
GRAPH_NODES(NODEID, LABEL, PROPERTIES)
GRAPH_EDGES(EDGEID, RELATIONSHIP_TYPE, SOURCENODEID, TARGETNODEID, PROPERTIES)
```

## Source Tables

The generated SQL reads the Snowflake MDM mirror tables:

```text
MDM_COMPANY
MDM_ADVISER
MDM_PERSON
MDM_SECURITY
MDM_FUND
MDM_RELATIONSHIP_TYPE
MDM_RELATIONSHIP_INSTANCE
```

Use `--mdm-database` and `--mdm-schema` when the mirror tables live outside the
default `EDGARTOOLS_<ENV>.MDM` location.

## Validation

Run validation directly with Snowflake CLI:

```bash
snow sql -c edgartools-dev -f .tmp/neo4j-snowflake-graph/01_validation.sql
```

Validation should show:

- `snowflake_graph_edges` equals active MDM relationship instances.
- `MDM_MINUS_GRAPH` is zero for active relationship types.
- The missing endpoint query returns no rows.

## Boundary

This document intentionally does not describe Aura, Bolt, Fleet tokens, or
external Neo4j password management. Those are not part of the supported
Snowflake-hosted graph analytics path.
