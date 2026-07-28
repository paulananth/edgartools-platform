-- GH-252: makes MDM_GRAPH_DASHBOARD actually enforce "access limited to a
-- dedicated read role" (GH-251 criterion 6) for anyone who *opens the app*,
-- not just for someone who manually `USE ROLE EDGARTOOLS_GRAPH_REVIEW_READER`.
--
-- Background: SELECT on the 5 MDM_GRAPH_REVIEW views alone
-- (01_graph_review_contract.sql) is not sufficient -- Streamlit-in-Snowflake
-- apps run with the app OWNER's privileges by default ("owner's rights"),
-- not the viewer's. Restricted caller's rights exists only as a Preview
-- feature for container-runtime apps, which this is not (see
-- docs.snowflake.com/en/developer-guide/streamlit/object-management/owners-rights).
-- infra/terraform/snowflake/accounts/{env}/main.tf's module.mdm_dashboard
-- creates MDM_GRAPH_DASHBOARD authenticated as the Terraform admin role
-- (ACCOUNTADMIN) -- so out of the box, every viewer with USAGE on the app
-- queries with ACCOUNTADMIN's full privileges through it, not
-- EDGARTOOLS_GRAPH_REVIEW_READER's scoped SELECT-only grants. The original
-- EDGARTOOLS_DASHBOARD has the identical gap (also ACCOUNTADMIN-owned),
-- deferred there since GH-247 (see deploy.sh's own header comment) -- not
-- fixed here, out of scope for this file.
--
-- Snowflake does not support `GRANT OWNERSHIP ... ON STREAMLIT` at all
-- (confirmed live: "Unsupported feature 'GRANT/REVOKE OWNERSHIP ON
-- STREAMLIT'") -- the only way to change a Streamlit object's owner is to
-- CREATE it while running AS the target role. This file's step 3 below does
-- exactly that: DROP the Terraform-created (ACCOUNTADMIN-owned) object and
-- recreate it identically while running as EDGARTOOLS_GRAPH_REVIEW_READER,
-- which owns nothing but the 5 views' SELECT + the schema/stage/warehouse
-- USAGE it needs to run -- so Owner's Rights now means exactly "this app
-- can see the 5 review views and nothing else."
--
-- Re-run this file (all statements are idempotent or safely re-driven) any
-- time module.mdm_dashboard's Terraform is re-applied and recreates the
-- Streamlit object -- that always re-creates it as ACCOUNTADMIN, since
-- Terraform authenticates as the admin role; this file is what puts
-- ownership back where it belongs.
--
-- Depends on infra/terraform/snowflake/accounts/{env}/main.tf's
-- module.mdm_dashboard already being applied (creates the
-- MDM_GRAPH_REVIEW_DASHBOARD schema + DASHBOARD_SRC stage, and an initial
-- ACCOUNTADMIN-owned MDM_GRAPH_DASHBOARD object this file replaces) --
-- run this SQL after that Terraform apply, not before. Also depends on
-- deploy.sh having staged real files onto DASHBOARD_SRC at least once
-- (CREATE STREAMLIT needs a populated root_location's main_file to exist).
--
-- Invoke with SnowCLI templating and
-- `-D database=EDGARTOOLS_PROD -D reader_warehouse=EDGARTOOLS_PROD_READER_WH`
-- (or the DEV equivalents, once GH-251's contract exists there), same
-- `{{ database }}` convention as 01_graph_review_contract.sql.

-- Step 1: make EDGARTOOLS_GRAPH_REVIEW_READER activatable at all.
-- GH-251's own contract SQL created the role and its SELECT grants on the 5
-- review views, but never granted the role itself to anyone -- confirmed
-- live via `SHOW GRANTS OF ROLE EDGARTOOLS_GRAPH_REVIEW_READER` returning no
-- rows, unlike EDGARTOOLS_{ENV}_READER (granted TO ROLE SYSADMIN). Mirrors
-- that same grant-to-SYSADMIN pattern.
GRANT ROLE EDGARTOOLS_GRAPH_REVIEW_READER TO ROLE SYSADMIN;

-- Step 2: everything the role needs to run the app once it owns it --
-- schema/warehouse USAGE, plus CREATE STREAMLIT + stage READ so it can
-- (re)create the object itself in step 3.
GRANT USAGE ON SCHEMA {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT USAGE ON WAREHOUSE {{ reader_warehouse }}
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT CREATE STREAMLIT ON SCHEMA {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
GRANT READ ON STAGE {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD.DASHBOARD_SRC
  TO ROLE EDGARTOOLS_GRAPH_REVIEW_READER;

-- Step 3: drop the ACCOUNTADMIN-owned object Terraform created and recreate
-- it identically as EDGARTOOLS_GRAPH_REVIEW_READER. Only the object's
-- OWNERSHIP row changes -- root_location/main_file/query_warehouse/title
-- are unchanged, and the staged files on DASHBOARD_SRC are untouched by
-- this (DROP STREAMLIT drops the pointer object, not the stage or its
-- files). Must run as ACCOUNTADMIN (or whichever role currently owns the
-- object) up to the DROP, then as EDGARTOOLS_GRAPH_REVIEW_READER for the
-- CREATE -- SnowCLI's --stdin session keeps one active role for the whole
-- script, so this step is written to be run as a script-level ROLE switch;
-- run interactively or split into two `snow sql` invocations if your
-- connection's default role cannot USE ROLE EDGARTOOLS_GRAPH_REVIEW_READER
-- (ACCOUNTADMIN can, by default).
DROP STREAMLIT IF EXISTS {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD.MDM_GRAPH_DASHBOARD;

USE ROLE EDGARTOOLS_GRAPH_REVIEW_READER;
USE WAREHOUSE {{ reader_warehouse }};
CREATE STREAMLIT {{ database }}.MDM_GRAPH_REVIEW_DASHBOARD.MDM_GRAPH_DASHBOARD
  ROOT_LOCATION = '@{{ database }}.MDM_GRAPH_REVIEW_DASHBOARD.DASHBOARD_SRC'
  MAIN_FILE = 'streamlit_app.py'
  QUERY_WAREHOUSE = '{{ reader_warehouse }}'
  TITLE = 'EdgarTools MDM Graph Review'
  COMMENT = 'EdgarTools prod gold-mirror dashboard.';
