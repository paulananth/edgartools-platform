-- GH-252: grants EDGARTOOLS_GRAPH_REVIEW_READER (created by
-- 01_graph_review_contract.sql) needs to actually open and query the
-- MDM_GRAPH_DASHBOARD Streamlit app -- SELECT on the 5 review views alone
-- is not sufficient to run a Streamlit-in-Snowflake app under that role.
--
-- Mirrors the grant pattern EDGARTOOLS_{ENV}_READER already holds for the
-- original dashboard (USAGE on its schema, its Streamlit object, and the
-- reader warehouse) -- see CLAUDE.md's manifest-pipeline incident notes for
-- why those three are each required, not just SELECT on the underlying
-- data.
--
-- Depends on infra/terraform/snowflake/accounts/{env}/main.tf's
-- module.mdm_dashboard already being applied (creates the
-- MDM_GRAPH_REVIEW_DASHBOARD schema + MDM_GRAPH_DASHBOARD Streamlit
-- object) -- run this SQL after that Terraform apply, not before.
--
-- Invoke with SnowCLI templating and
-- `-D database=EDGARTOOLS_PROD -D reader_warehouse=EDGARTOOLS_PROD_READER_WH`
-- (or the DEV equivalents, once GH-251's contract exists there), same
-- `{{ database }}` convention as 01_graph_review_contract.sql.

-- GH-251's own contract SQL created EDGARTOOLS_GRAPH_REVIEW_READER and its
-- SELECT grants on the 5 review views, but never granted the role itself to
-- anyone -- confirmed live via `SHOW GRANTS OF ROLE
-- EDGARTOOLS_GRAPH_REVIEW_READER` returning no rows, unlike
-- EDGARTOOLS_{ENV}_READER (granted TO ROLE SYSADMIN). Without this, no
-- user/role could ever activate EDGARTOOLS_GRAPH_REVIEW_READER, so the
-- Streamlit app's Caller's Rights queries would fail for every viewer.
-- Mirrors EDGARTOOLS_{ENV}_READER's own grant-to-SYSADMIN pattern.
GRANT ROLE EDGARTOOLS_GRAPH_REVIEW_READER TO ROLE SYSADMIN;

GRANT USAGE ON SCHEMA {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT USAGE ON STREAMLIT {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD.MDM_GRAPH_DASHBOARD
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT USAGE ON WAREHOUSE {{ reader_warehouse }}
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
