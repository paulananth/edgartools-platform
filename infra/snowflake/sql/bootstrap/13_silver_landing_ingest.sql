-- Snowflake silver-landing ingest apparatus: the stage, file format, load
-- procedure, and scheduled task that actually load the Parquet
-- edgar_warehouse/serving/silver_landing_writer.py produces into
-- EDGARTOOLS_SILVER_LANDING's 30 tables (11_silver_landing_schema.sql
-- created the schema/tables/grants; nothing downstream of that read them
-- until this file).
--
-- silver-snowflake-migration map, Ticket 07's decision, in full:
--   - A NEW, ISOLATED apparatus -- does not touch native_pull's existing
--     Terraform resources (the live EDGARTOOLS_SOURCE/gold-refresh chain
--     every gold table depends on today).
--   - A plain SCHEDULED TASK running COPY INTO per table, not
--     Snowpipe-auto-ingest + stream + manifest. Landing is pure append (no
--     MERGE target to resolve), and COPY INTO already tracks per-file load
--     history and skips files it has already loaded -- the manifest/stream
--     indirection SOURCE's apparatus needs for MERGE-key resolution buys
--     nothing here. Traded away: event-driven latency (seconds) for
--     scheduled-poll latency (this task's SCHEDULE); acceptable because
--     nothing downstream reads EDGARTOOLS_SILVER_LANDING synchronously --
--     Ticket 01's dbt silver dynamic_table models refresh on their own
--     TARGET_LAG, not on landing's write latency.
--   - SAME BUCKET as SERVING_EXPORT_ROOT, new "silver_landing/" prefix.
--     Snowflake's STORAGE_ALLOWED_LOCATIONS is an exact-prefix allowlist
--     (confirmed live against native_pull's storage integration -- it was a
--     single exact URL, not a whole-bucket grant), so this required one
--     additive Terraform change (native_pull's new
--     additional_storage_locations variable) applied BEFORE this script:
--     infra/terraform/snowflake/modules/native_pull/{main,variables}.tf,
--     infra/terraform/snowflake/accounts/prod/main.tf.
--
-- Full design context: .scratch/silver-snowflake-migration/map.md, Ticket 07.
--
-- Run once per environment, AFTER 11_silver_landing_schema.sql,
-- 12_silver_schema_and_mdm_reader.sql, and the storage-integration widen
-- above have all landed (idempotent, safe to re-run):
--   snow sql --connection edgartools-prod -f infra/snowflake/sql/bootstrap/13_silver_landing_ingest.sql
--
-- Ownership: unlike 11_/12_ (schema/tables created under ACCOUNTADMIN, then
-- granted to the loader), the procedure and task below are created DIRECTLY
-- AS EDGARTOOLS_PROD_LOADER -- a scheduled task and the procedure it calls
-- are the actual running pipeline (not passive schema/data objects), and
-- CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax incident"
-- documents an explicit user instruction that ad-hoc ACCOUNTADMIN ownership
-- is not an acceptable pattern for pipeline objects. This requires granting
-- the loader CREATE FILE FORMAT/STAGE/PROCEDURE/TASK on the schema plus the
-- account-level EXECUTE TASK privilege first (ACCOUNTADMIN-only grants,
-- done once below) -- everything after the role switch is additive/
-- idempotent (CREATE ... IF NOT EXISTS or CREATE OR REPLACE PROCEDURE, which
-- has no meaningful "already exists, leave it" state), never a REVOKE, DROP,
-- or ownership transfer.

USE ROLE ACCOUNTADMIN;
USE DATABASE EDGARTOOLS_PROD;

-- 11_silver_landing_schema.sql granted the loader USAGE/SELECT/INSERT on
-- this schema (data access) -- not the CREATE privileges needed to
-- provision new objects directly as that role. Storage-integration USAGE is
-- also required before a non-ACCOUNTADMIN role can CREATE STAGE against it.
GRANT USAGE ON INTEGRATION EDGARTOOLS_PROD_EXPORT_INTEGRATION TO ROLE EDGARTOOLS_PROD_LOADER;
GRANT CREATE FILE FORMAT, CREATE STAGE, CREATE PROCEDURE, CREATE TASK
    ON SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING TO ROLE EDGARTOOLS_PROD_LOADER;
-- Account-level privilege; only ACCOUNTADMIN can grant it. Without this a
-- loader-owned task cannot execute on its schedule at all, regardless of
-- what OPERATE/MONITOR grants it holds on the task itself.
GRANT EXECUTE TASK ON ACCOUNT TO ROLE EDGARTOOLS_PROD_LOADER;
-- Deliberate, narrow reversal of 11_silver_landing_schema.sql's stated
-- policy ("SELECT + INSERT only... granting UPDATE would be a standing
-- capability with no legitimate caller"): LOAD_SILVER_LANDING's
-- parse_sequence backfill (see procedure body below) is now that legitimate
-- caller -- verified live that COPY INTO ... MATCH_BY_COLUMN_NAME does not
-- invoke a target column's DEFAULT for a column absent from the source
-- file, so parse_sequence must be backfilled via UPDATE after each COPY.
-- The grant is table-wide (Snowflake has no column-level UPDATE privilege),
-- but the only SQL ever run under it is this procedure's single hardcoded
-- `UPDATE ... SET parse_sequence = ... WHERE parse_sequence IS NULL`
-- statement -- EXECUTE AS OWNER means no other caller gains UPDATE access
-- through this grant.
GRANT UPDATE ON ALL TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING TO ROLE EDGARTOOLS_PROD_LOADER;
GRANT UPDATE ON FUTURE TABLES IN SCHEMA EDGARTOOLS_PROD.EDGARTOOLS_SILVER_LANDING TO ROLE EDGARTOOLS_PROD_LOADER;

USE ROLE EDGARTOOLS_PROD_LOADER;
USE DATABASE EDGARTOOLS_PROD;
USE SCHEMA EDGARTOOLS_SILVER_LANDING;

CREATE FILE FORMAT IF NOT EXISTS PARQUET_FORMAT
    TYPE = PARQUET
    COMPRESSION = AUTO
    COMMENT = 'Parquet file format for the silver-landing zone (Ticket 07).';

-- URL matches Terraform's silver_landing_export_root_url output exactly
-- (accounts/prod/main.tf's local: export_root_url with "snowflake_exports/"
-- swapped for "silver_landing/") -- keep the two in lockstep if
-- export_root_url's bucket or prefix ever changes.
CREATE STAGE IF NOT EXISTS LANDING_STAGE
    URL = 's3://edgartools-prod-snowflake-export-690839588395/warehouse/artifacts/silver_landing/'
    STORAGE_INTEGRATION = EDGARTOOLS_PROD_EXPORT_INTEGRATION
    FILE_FORMAT = PARQUET_FORMAT
    COMMENT = 'External stage over the silver-landing zone Parquet export (Ticket 07).';

-- One procedure, COPY + backfill per table -- a fixed, hardcoded table list
-- rather than a query-driven cursor (sidesteps the multi-column FOR-row
-- cursor defect CLAUDE.md's "Manifest-pipeline ownership + cursor-syntax
-- incident" documents; there is no query here to iterate, so it doesn't
-- apply, but a hardcoded JS array is simpler and safer regardless). The
-- table list matches 11_silver_landing_schema.sql's 31 tables exactly --
-- regenerate both together if silver_store.py's schema changes
-- (generate_silver_landing_ddl.py is the source of truth for the list).
--
-- MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE: the Parquet files
-- silver_landing_writer.py produces carry only the domain columns a given
-- parse actually populated (pa.Table.from_pylist(rows), no parse_sequence
-- column -- that's server-assigned via each table's PARSE_SEQ.NEXTVAL
-- DEFAULT).
--
-- COPY + UPDATE, not COPY alone: verified LIVE (not assumed from docs) with
-- a hand-built single-row Parquet file that COPY INTO ... MATCH_BY_COLUMN_NAME
-- does NOT invoke a target column's DEFAULT for a column absent from the
-- source file -- it leaves it NULL, which failed outright against
-- parse_sequence's original NOT NULL constraint ("NULL result in a
-- non-nullable column"). Fix, in two parts: 11_silver_landing_schema.sql's
-- parse_sequence column dropped NOT NULL (Snowflake PRIMARY KEY is
-- declarative-only, unenforced, so this doesn't weaken anything real), and
-- this procedure now follows every COPY INTO with an UPDATE that backfills
-- parse_sequence for exactly the rows that COPY just landed (an equality
-- filter on `? IS NULL` after each table's own COPY is safe -- no other
-- writer ever produces a NULL parse_sequence row, so this can't accidentally
-- backfill a stale/unrelated row from a previous run). Re-verified live
-- end-to-end with the same hand-built file before this procedure was
-- trusted with the full table list (see Ticket 07's Answer for that
-- verification's result).
--
-- EXECUTE AS OWNER + loader ownership (see file header) means this runs
-- with the loader's own SELECT/INSERT grants on these tables -- no separate
-- runtime-privilege grant needed beyond 11_'s existing INSERT grant.
CREATE OR REPLACE PROCEDURE LOAD_SILVER_LANDING()
RETURNS VARIANT
LANGUAGE JAVASCRIPT
EXECUTE AS OWNER
AS
$$
const tables = [
  "sec_accounting_flag", "sec_adv_disclosure_event", "sec_adv_filing",
  "sec_adv_firm_roster", "sec_adv_office", "sec_adv_private_fund",
  "sec_auditor_report_evidence", "sec_company", "sec_company_address",
  "sec_company_filing", "sec_company_former_name",
  "sec_company_submission_file", "sec_company_ticker",
  "sec_current_filing_feed", "sec_earnings_release", "sec_employment_event",
  "sec_executive_record", "sec_filing_attachment", "sec_filing_text",
  "sec_financial_derived", "sec_financial_fact", "sec_guidance_fact",
  "sec_guidance_fact_reject", "sec_ownership_derivative_txn",
  "sec_ownership_non_derivative_txn", "sec_ownership_reporting_owner",
  "sec_pcaob_firm_identity", "sec_raw_object", "sec_subsidiary_evidence",
  "sec_thirteenf_filing", "sec_thirteenf_holding",
];

const results = [];
let totalRowsLoaded = 0;

for (const table of tables) {
  const copyStatement = `
    COPY INTO ${table}
    FROM @LANDING_STAGE/${table}/
    FILE_FORMAT = (FORMAT_NAME = PARQUET_FORMAT)
    MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
    PATTERN = '.*[.]parquet'
    ON_ERROR = ABORT_STATEMENT
  `;
  const copyStmt = snowflake.createStatement({sqlText: copyStatement});
  const rs = copyStmt.execute();

  // COPY INTO's result set shape depends on outcome, verified live against
  // both cases (not assumed): when files actually load, it's the documented
  // 10-column per-file shape (file, status, rows_parsed, rows_loaded, ...);
  // when NO files match the pattern, it's a DIFFERENT single-column shape
  // (one row, one "status" column reading e.g. "Copy executed with 0 files
  // processed."). Column count, not row presence, is what distinguishes
  // them -- rs.next() is true in BOTH cases, so checking column count first
  // is required, not optional. rows_loaded is column 4 (1-indexed) only in
  // the 10-column shape; getColumnValue('rows_loaded') by name was tried
  // first and confirmed live to throw ("Given column name/index does not
  // exist") -- positional index is what the JS Stored Proc API actually
  // supports here.
  let filesProcessed = 0;
  let rowsLoaded = 0;
  if (copyStmt.getColumnCount() > 1) {
    while (rs.next()) {
      filesProcessed += 1;
      rowsLoaded += rs.getColumnValue(4) || 0;
    }
  }

  if (filesProcessed > 0) {
    snowflake.createStatement({
      sqlText: `UPDATE ${table} SET parse_sequence = PARSE_SEQ.NEXTVAL WHERE parse_sequence IS NULL`
    }).execute();
    results.push({table: table, files_processed: filesProcessed, rows_loaded: rowsLoaded});
    totalRowsLoaded += rowsLoaded;
  }
}

return {
  status: "succeeded",
  tables_with_new_data: results.length,
  total_rows_loaded: totalRowsLoaded,
  detail: results,
};
$$;

-- 5-minute cadence: a starting default, not load-bearing on anything
-- downstream yet (Ticket 07's Answer) -- tune once real volume exists.
-- Reuses EDGARTOOLS_PROD_REFRESH_WH, the warehouse already used for this
-- account's other lightweight scheduled/refresh work; no new warehouse.
-- Loader already holds USAGE on this warehouse (it is dbt's prod target's
-- warehouse too) -- no additional grant needed for the task to run on it.
CREATE TASK IF NOT EXISTS LOAD_SILVER_LANDING_TASK
    WAREHOUSE = EDGARTOOLS_PROD_REFRESH_WH
    SCHEDULE = '5 MINUTE'
    COMMENT = 'Scheduled COPY INTO of the silver-landing Parquet export (Ticket 07).'
AS
    CALL LOAD_SILVER_LANDING();

-- Tasks are created SUSPENDED by default -- must be explicitly resumed to
-- actually run on schedule (same real Snowflake behavior the manifest-task
-- suspension incident above documents for a different task). Documented
-- live (not assumed) to be a no-op, not an error, when re-run against an
-- already-started task -- see Ticket 07's Answer for the re-run test result.
ALTER TASK LOAD_SILVER_LANDING_TASK RESUME;
