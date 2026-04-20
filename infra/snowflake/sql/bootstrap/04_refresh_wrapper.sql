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
  "FILING_DETAIL"
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
BEGIN
  FOR manifest_record IN (
    SELECT DISTINCT workflow_name, run_id
    FROM EDGARTOOLS_SOURCE.SNOWFLAKE_RUN_MANIFEST_STREAM
    WHERE METADATA$ACTION = 'INSERT'
  ) DO
    CALL EDGARTOOLS_SOURCE.LOAD_EXPORTS_FOR_RUN(manifest_record.workflow_name, manifest_record.run_id);
    CALL EDGARTOOLS_GOLD.REFRESH_AFTER_LOAD(manifest_record.workflow_name, manifest_record.run_id);
  END FOR;

  RETURN OBJECT_CONSTRUCT('status', 'succeeded');
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
