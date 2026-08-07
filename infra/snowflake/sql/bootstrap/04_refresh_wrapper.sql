-- Create the public Snowflake refresh wrapper and triggered manifest-processing task.
--
-- Required session variables:
--   set database_name = 'EDGARTOOLS_DEV';
--   set source_schema_name = 'EDGARTOOLS_SOURCE';
--   set gold_schema_name = 'EDGARTOOLS_GOLD';
--   set deployer_role_name = 'EDGARTOOLS_DEV_DEPLOYER';
--   set refresh_warehouse_name = 'EDGARTOOLS_DEV_REFRESH_WH';
--   set manifest_stream_name = 'SNOWFLAKE_RUN_MANIFEST_STREAM';
--   set source_load_procedure_name = 'LOAD_EXPORTS_FOR_RUN';
--   set refresh_procedure_name = 'REFRESH_AFTER_LOAD';
--   set stream_processor_procedure_name = 'PROCESS_RUN_MANIFEST_STREAM';
--   set manifest_task_name = 'SNOWFLAKE_RUN_MANIFEST_TASK';

USE ROLE IDENTIFIER($deployer_role_name);
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($gold_schema_name);

CREATE OR REPLACE PROCEDURE IDENTIFIER($refresh_procedure_name)(workflow_name STRING, run_id STRING)
RETURNS VARIANT
LANGUAGE JAVASCRIPT
EXECUTE AS OWNER
AS
$$
const currentDatabase = snowflake.createStatement({sqlText: "SELECT CURRENT_DATABASE()"}).execute();
currentDatabase.next();
const databaseName = currentDatabase.getColumnValue(1);
const sourceSchema = "EDGARTOOLS_SOURCE";
const goldSchema = "EDGARTOOLS_GOLD";
const statusTable = `${databaseName}.${sourceSchema}.SNOWFLAKE_REFRESH_STATUS`;
const refreshHistoryFunction = `${databaseName}.INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY`;
const goldTables = [
  "COMPANY",
  "FILING_ACTIVITY",
  "OWNERSHIP_ACTIVITY",
  "OWNERSHIP_HOLDINGS",
  "ADVISER_OFFICES",
  "ADVISER_DISCLOSURES",
  "PRIVATE_FUNDS",
  "FILING_DETAIL",
  "TICKER_REFERENCE",
  // "Isolated DAG branch" gold models (target_lag=DOWNSTREAM, zero ref()
  // edges into the original 9-table chain above -- nothing else ever drives
  // their refresh, so they must be refreshed explicitly here or they never
  // refresh again after their empty initialize=ON_CREATE run). Found
  // 2026-07-26: all 6 had zero refresh history in prod despite non-empty
  // EDGARTOOLS_SOURCE data once gold-refresh finally ran for the first
  // time. FINANCIAL_FACTORS must stay after FINANCIAL_DERIVED -- it's a
  // real dbt ref() dependency, not a source(), and Snowflake does not
  // cascade a DOWNSTREAM-lag refresh across ref() edges on its own.
  "EXECUTIVE_RECORDS",
  "EARNINGS_RELEASES",
  "INSTITUTIONAL_HOLDINGS",
  "ACCOUNTING_FLAGS",
  "FINANCIAL_FACTS",
  "FINANCIAL_DERIVED",
  "FINANCIAL_FACTORS",
  // Explore-layer isolated DAG branches (ERDP-01/02/03) -- same
  // "never refreshes again after ON_CREATE" hazard as the block above.
  // EARNINGS_CALENDAR shipped with ERDP-03 (merged to main before this
  // allowlist gap was found) and was live-broken until this line landed;
  // GUIDANCE_FACTS (ERDP-02), CONSENSUS_ESTIMATES (ERDP-01), and
  // TRANSCRIPT_EVENTS (ERDP-04) each ship in the same PR that adds their
  // entry, so none ran unregistered.
  "EARNINGS_CALENDAR",
  "GUIDANCE_FACTS",
  "CONSENSUS_ESTIMATES",
  "TRANSCRIPT_EVENTS",
  // Found while implementing the snowflake-account-cutover map's gold-verify-
  // live check (wayfinder ticket 06): ADV_FUND_COUNT_RECONCILIATION
  // (.scratch/adv-firm-roster-crosscheck/) shipped after this allowlist gap
  // was fixed for the tables above and was never added here -- same
  // isolated-DAG-branch hazard, source()-only, no ref() edges into any
  // other gold model.
  "ADV_FUND_COUNT_RECONCILIATION"
];
const pollIntervalSeconds = 5;
const timeoutSeconds = 900;

function q(value) {
  if (value === null || value === undefined) {
    return null;
  }
  return String(value).replace(/'/g, "''");
}

function exec(sqlText) {
  return snowflake.createStatement({sqlText}).execute();
}

function scalar(sqlText) {
  const rs = exec(sqlText);
  rs.next();
  return rs.getColumnValue(1);
}

function updateRefreshStatus(refreshStatus, status, errorMessage, succeeded) {
  const errorValue = errorMessage === null || errorMessage === undefined ? "NULL" : `'${q(errorMessage)}'`;
  exec(`
    UPDATE ${statusTable}
    SET
      refresh_status = '${q(refreshStatus)}',
      status = '${q(status)}',
      error_message = ${errorValue},
      last_successful_refresh_at = ${succeeded ? "CURRENT_TIMESTAMP()" : "last_successful_refresh_at"},
      updated_at = CURRENT_TIMESTAMP()
    WHERE source_workflow = '${q(WORKFLOW_NAME)}'
      AND run_id = '${q(RUN_ID)}'
      AND source_load_status = 'succeeded'
  `);
}

function waitForRefresh(qualifiedTable) {
  const refreshStartedAt = scalar("SELECT TO_VARCHAR(CURRENT_TIMESTAMP())");
  exec(`ALTER DYNAMIC TABLE ${qualifiedTable} REFRESH`);

  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const rs = exec(`
      SELECT
        STATE,
        STATE_MESSAGE,
        REFRESH_ACTION,
        REFRESH_TRIGGER,
        TO_VARCHAR(COALESCE(REFRESH_START_TIME, DATA_TIMESTAMP)) AS STARTED_AT,
        TO_VARCHAR(REFRESH_END_TIME) AS ENDED_AT
      FROM TABLE(${refreshHistoryFunction}(
        NAME => '${q(qualifiedTable)}',
        RESULT_LIMIT => 20
      ))
      WHERE REFRESH_TRIGGER = 'MANUAL'
        AND COALESCE(REFRESH_START_TIME, DATA_TIMESTAMP) >= TO_TIMESTAMP_TZ('${q(refreshStartedAt)}')
      ORDER BY COALESCE(REFRESH_START_TIME, DATA_TIMESTAMP) DESC
      LIMIT 1
    `);

    if (rs.next()) {
      const state = String(rs.getColumnValue(1) || "").toUpperCase();
      const stateMessage = rs.getColumnValue(2);
      if (state === "SUCCEEDED") {
        return {
          table_name: qualifiedTable,
          state: state,
          state_message: stateMessage,
          refresh_action: rs.getColumnValue(3),
          refresh_trigger: rs.getColumnValue(4),
          started_at: rs.getColumnValue(5),
          ended_at: rs.getColumnValue(6)
        };
      }
      if (["FAILED", "UPSTREAM_FAILED", "CANCELLED"].includes(state)) {
        throw new Error(`Dynamic table refresh failed for ${qualifiedTable}: ${stateMessage || state}`);
      }
    }

    exec(`SELECT SYSTEM$WAIT(${pollIntervalSeconds}, 'SECONDS')`);
  }

  throw new Error(`Timed out waiting for dynamic table refresh for ${qualifiedTable}.`);
}

const readyRowCount = Number(scalar(`
  SELECT COUNT(*)
  FROM ${statusTable}
  WHERE source_workflow = '${q(WORKFLOW_NAME)}'
    AND run_id = '${q(RUN_ID)}'
    AND source_load_status = 'succeeded'
`));

if (readyRowCount === 0) {
  throw new Error(`No successful source-load status row found for workflow ${WORKFLOW_NAME} and run ${RUN_ID}.`);
}

updateRefreshStatus("running", "running", null, false);

const refreshedTables = [];
try {
  for (const tableName of goldTables) {
    const qualifiedTable = `${databaseName}.${goldSchema}.${tableName}`;
    refreshedTables.push(waitForRefresh(qualifiedTable));
  }

  updateRefreshStatus("succeeded", "succeeded", null, true);

  return {
    status: "succeeded",
    workflow_name: WORKFLOW_NAME,
    run_id: RUN_ID,
    refreshed_tables: refreshedTables
  };
} catch (error) {
  updateRefreshStatus("failed", "failed", error.message, false);
  throw error;
}
$$;

CREATE OR REPLACE PROCEDURE IDENTIFIER($stream_processor_procedure_name)()
RETURNS VARIANT
LANGUAGE SQL
EXECUTE AS OWNER
AS
$$
-- Found 2026-07-27: the shorthand `FOR record IN (SELECT col1, col2 FROM ...)
-- DO` cursor construct (this exact procedure body) started failing with
-- "Unsupported: Scalar subquery with multi-column SELECT clause" --
-- independently reproduced live with a trivial literal two-column SELECT
-- unrelated to any table. Not a "never worked" case: TASK_HISTORY shows this
-- same procedure succeeded as recently as 2026-07-26 16:53:53, under a day
-- before the failures started, so treat this as a real but not fully
-- understood intermittent defect in the multi-column shorthand form, not a
-- permanent account-wide break. See CLAUDE.md's manifest-pipeline ownership
-- + cursor-syntax incident 5-whys for the full timeline. The explicit
-- CURSOR / OPEN / FETCH form below (with a pre-computed row count, since a
-- naive FETCH-until-not-found loop also hung under this same account state)
-- is the workaround in use here.
DECLARE
  cnt INTEGER;
  c1 CURSOR FOR
    SELECT DISTINCT workflow_name, run_id
    FROM EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM
    WHERE METADATA$ACTION = 'INSERT';
  r_workflow_name STRING;
  r_run_id STRING;
BEGIN
  cnt := (
    SELECT COUNT(*) FROM (
      SELECT DISTINCT workflow_name, run_id
      FROM EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM
      WHERE METADATA$ACTION = 'INSERT'
    )
  );
  OPEN c1;
  FOR i IN 1 TO cnt DO
    FETCH c1 INTO r_workflow_name, r_run_id;
    CALL EDGARTOOLS_SOURCE.LOAD_EXPORTS_FOR_RUN(:r_workflow_name, :r_run_id);
    CALL EDGARTOOLS_GOLD.REFRESH_AFTER_LOAD(:r_workflow_name, :r_run_id);
  END FOR;
  CLOSE c1;

  RETURN OBJECT_CONSTRUCT('status', 'succeeded', 'processed', cnt);
END;
$$;

BEGIN
  EXECUTE IMMEDIATE
    'CREATE OR REPLACE TASK ' || $manifest_task_name || '
       WAREHOUSE = ' || $refresh_warehouse_name || '
       WHEN SYSTEM$STREAM_HAS_DATA(''' || $database_name || '.' || $source_schema_name || '.' || $manifest_stream_name || ''')
       AS
       CALL ' || $database_name || '.' || $gold_schema_name || '.' || $stream_processor_procedure_name || '()';
END;

BEGIN
  EXECUTE IMMEDIATE
    'ALTER TASK ' || $manifest_task_name || ' RESUME';
END;
