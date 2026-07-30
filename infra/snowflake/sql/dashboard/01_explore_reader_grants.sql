-- Bounded Explore workflow dependencies for GH-248/GH-249/GH-250/GH-253.
-- The Streamlit object runs with the dedicated owner's rights.  Gold access
-- remains inherited from the bounded reader role; graph access is explicit
-- and read-only because graph objects live outside EDGARTOOLS_GOLD.
--
-- Invoke with:
-- snow sql -D database=EDGARTOOLS_PROD \
--   -D dashboard_owner_role=EDGARTOOLS_PROD_DASHBOARD_OWNER \
--   -f infra/snowflake/sql/dashboard/01_explore_reader_grants.sql

GRANT USAGE ON SCHEMA {{ database }}.NEO4J_GRAPH_MIGRATION
  TO ROLE {{ dashboard_owner_role }};
GRANT SELECT ON TABLE {{ database }}.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_NODES
  TO ROLE {{ dashboard_owner_role }};
GRANT SELECT ON TABLE {{ database }}.NEO4J_GRAPH_MIGRATION.MDM_GRAPH_EDGES
  TO ROLE {{ dashboard_owner_role }};
GRANT SELECT ON TABLE {{ database }}.NEO4J_GRAPH_MIGRATION.GRAPH_ACTIVE_POINTER
  TO ROLE {{ dashboard_owner_role }};
