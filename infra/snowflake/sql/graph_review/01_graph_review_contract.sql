-- GH-251: generation-scoped Snowflake graph-review contract.
--
-- Publishes the useful MDM/hosted-graph review state (the payload
-- `edgar-warehouse mdm reconcile` already computes -- see
-- edgar_warehouse/mdm/snowflake_graph.py's SnowflakeGraphVerifier and
-- edgar_warehouse/mdm/graph_review_publish.py) as bounded, read-only
-- Snowflake objects, so a managed dashboard (GH-252) can inspect the active
-- generation through a plain Snowpark session -- no MDM Postgres DSN, no
-- direct Neo4j connection, no MDM_SNOWFLAKE_*/DBT_SNOWFLAKE_* service
-- credential.
--
-- Deliberately a SEPARATE schema from NEO4J_GRAPH_MIGRATION, not a new set
-- of objects inside it: NEO4J_GRAPH_MIGRATION already grants
-- `SELECT ON FUTURE TABLES/VIEWS` to EDGARTOOLS_GRAPH_APP_USER and the
-- Neo4j Graph Analytics Native App's database role
-- (neo4j_graph_analytics_app_grants.sql) -- landing review objects there
-- would make them automatically readable by roles that also see the raw
-- MDM_GRAPH_NODES/MDM_GRAPH_EDGES tables, undercutting "access is limited
-- to a dedicated read role" and "sensitive properties... excluded".
--
-- Fail-closed on stale/mixed generations (GH-251 criterion 2): every public
-- view joins its persisted rows to GRAPH_ACTIVE_POINTER
-- (NEO4J_GRAPH_MIGRATION, the platform's single guarded activation pointer)
-- on GENERATION_ID. If verify-graph published rows for a generation that is
-- no longer the active one -- e.g. it ran against a candidate that was later
-- rolled back, or activation moved on before the review rows were refreshed
-- -- the view returns zero rows rather than silently serving stale parity/
-- diagnostics as if they were current. A consuming dashboard renders zero
-- rows as "stale/unavailable", never as "healthy: no mismatches".
--
-- Invoke with SnowCLI templating and `-D database=EDGARTOOLS_DEV` (or PROD),
-- same convention as neo4j_graph_analytics_app_grants.sql. NOT applied to
-- live Snowflake by this commit -- see PR description.

CREATE SCHEMA IF NOT EXISTS {{ database }}.MDM_GRAPH_REVIEW;

-- Per-entity-type node parity for one generation, as computed by
-- SnowflakeGraphVerifier.verify()'s node_parity.by_entity_type. Replaced
-- wholesale per generation on each verify-graph run (DELETE + INSERT scoped
-- to GENERATION_ID, never UPDATE) -- see graph_review_publish.py.
CREATE TABLE IF NOT EXISTS {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_ENTITY_PARITY (
  GENERATION_ID STRING NOT NULL,
  ENTITY_TYPE STRING NOT NULL,
  MDM_ACTIVE_COUNT NUMBER NOT NULL,
  GRAPH_NODE_COUNT NUMBER NOT NULL,
  MDM_MINUS_GRAPH NUMBER NOT NULL,
  GRAPH_MINUS_MDM NUMBER NOT NULL,
  STATUS STRING NOT NULL,
  PUBLISHED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Per-relationship-type edge parity, mirrors GRAPH_REVIEW_ENTITY_PARITY.
CREATE TABLE IF NOT EXISTS {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_RELATIONSHIP_PARITY (
  GENERATION_ID STRING NOT NULL,
  RELATIONSHIP_TYPE STRING NOT NULL,
  MDM_ACTIVE_COUNT NUMBER NOT NULL,
  GRAPH_EDGE_COUNT NUMBER NOT NULL,
  MDM_MINUS_GRAPH NUMBER NOT NULL,
  GRAPH_MINUS_MDM NUMBER NOT NULL,
  STATUS STRING NOT NULL,
  PUBLISHED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Bounded mismatch samples (missing/extra nodes, missing/extra edges,
-- missing edge endpoints) -- the same sample_limit-capped rows
-- verify-graph's diagnostics already returns, never a raw unrestricted
-- diagnostic dump (GH-251 criterion 3).
CREATE TABLE IF NOT EXISTS {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_MISMATCH_SAMPLE (
  GENERATION_ID STRING NOT NULL,
  SAMPLE_TYPE STRING NOT NULL, -- missing_graph_nodes | extra_graph_nodes |
                                -- missing_graph_edges | extra_graph_edges |
                                -- missing_graph_edge_endpoints
  ENTITY_TYPE STRING,
  RELATIONSHIP_TYPE STRING,
  NODE_ID STRING,
  EDGE_ID STRING,
  SOURCE_NODE_ID STRING,
  TARGET_NODE_ID STRING,
  PUBLISHED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Native App (Neo4j Graph Analytics) check results from the same
-- verify-graph run -- compute pool, GRAPH_INFO, BFS, WCC (see
-- SnowflakeGraphVerificationConfig.verify_native_app).
CREATE TABLE IF NOT EXISTS {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_NATIVE_APP_CHECK (
  GENERATION_ID STRING NOT NULL,
  CHECK_NAME STRING NOT NULL,
  STATUS STRING NOT NULL,
  DETAIL STRING,
  REMEDIATION STRING,
  PUBLISHED_AT TIMESTAMP_TZ NOT NULL DEFAULT CURRENT_TIMESTAMP()
);

-- Read-only, generation-scoped, fail-closed views. These -- not the base
-- tables above -- are what EDGARTOOLS_GRAPH_REVIEW_READER is granted SELECT
-- on, so a stale write pattern (or a future column added to a base table)
-- can't leak un-reviewed shape into the published contract.

CREATE OR REPLACE VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_ACTIVE_GENERATION AS
SELECT
  ptr.ACTIVE_GENERATION_ID AS GENERATION_ID,
  ptr.ACTIVATED_AT,
  g.STATUS,
  g.RULE_VERSION,
  g.SCHEMA_VERSION,
  g.NODE_COUNT,
  g.EDGE_COUNT,
  g.CREATED_AT,
  g.VERIFIED_AT
FROM {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER ptr
JOIN {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_GENERATION g
  ON g.GENERATION_ID = ptr.ACTIVE_GENERATION_ID;

CREATE OR REPLACE VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_ENTITY_PARITY AS
SELECT p.*
FROM {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_ENTITY_PARITY p
JOIN {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER ptr
  ON p.GENERATION_ID = ptr.ACTIVE_GENERATION_ID;

CREATE OR REPLACE VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_RELATIONSHIP_PARITY AS
SELECT p.*
FROM {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_RELATIONSHIP_PARITY p
JOIN {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER ptr
  ON p.GENERATION_ID = ptr.ACTIVE_GENERATION_ID;

CREATE OR REPLACE VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_MISMATCH_SAMPLE AS
SELECT s.*
FROM {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_MISMATCH_SAMPLE s
JOIN {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER ptr
  ON s.GENERATION_ID = ptr.ACTIVE_GENERATION_ID;

CREATE OR REPLACE VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_NATIVE_APP_CHECK AS
SELECT c.*
FROM {{ database }}.MDM_GRAPH_REVIEW.GRAPH_REVIEW_NATIVE_APP_CHECK c
JOIN {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER ptr
  ON c.GENERATION_ID = ptr.ACTIVE_GENERATION_ID;

-- Dedicated read role (GH-251 criterion 6). SELECT on the 5 views only --
-- never the base MDM_GRAPH_REVIEW tables, never NEO4J_GRAPH_MIGRATION
-- objects, never raw MDM_GRAPH_NODES/MDM_GRAPH_EDGES.
CREATE ROLE IF NOT EXISTS EDGARTOOLS_GRAPH_REVIEW_READER;

GRANT USAGE ON DATABASE {{ database }}
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT USAGE ON SCHEMA {{ database }}.MDM_GRAPH_REVIEW
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT SELECT ON VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_ACTIVE_GENERATION
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT SELECT ON VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_ENTITY_PARITY
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT SELECT ON VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_RELATIONSHIP_PARITY
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT SELECT ON VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_MISMATCH_SAMPLE
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT SELECT ON VIEW {{ database }}.MDM_GRAPH_REVIEW.V_GRAPH_REVIEW_NATIVE_APP_CHECK
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;

-- The writer role (whatever runs `mdm reconcile` -- MDM_SNOWFLAKE_ROLE/
-- DBT_SNOWFLAKE_ROLE per edgar_warehouse/mdm/export.py's
-- SnowflakeConnectionSettings) needs write access to the 4 base tables.
-- Grant this to that role by name once it's finalized for the target
-- environment; left as a documented TODO rather than guessed here, since
-- that role name is environment-specific and this file must stay
-- environment-agnostic (see {{ database }} templating above).
