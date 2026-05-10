CREATE OR REPLACE PROCEDURE __STREAM_PROCESSOR_PROCEDURE_NAME__()
RETURNS VARIANT
LANGUAGE JAVASCRIPT
EXECUTE AS OWNER
AS
$$
const currentDatabase = snowflake.createStatement({sqlText: "SELECT CURRENT_DATABASE()"}).execute();
currentDatabase.next();
const databaseName = currentDatabase.getColumnValue(1);
const sourceSchema = "__SOURCE_SCHEMA__";
const goldSchema = "__GOLD_SCHEMA__";
const manifestStream = `${databaseName}.${sourceSchema}.__MANIFEST_STREAM_NAME__`;
const sourceLoadProcedure = `${databaseName}.${sourceSchema}.__SOURCE_LOAD_PROCEDURE_NAME__`;
const refreshProcedure = `${databaseName}.${goldSchema}.__REFRESH_PROCEDURE_NAME__`;
const tempManifestTable = `TMP_RUN_MANIFEST_STREAM_${Date.now()}`;

snowflake.createStatement({
  sqlText: `CREATE TEMP TABLE ${tempManifestTable} (workflow_name STRING, run_id STRING)`
}).execute();

// Reading a stream with SELECT does not advance its offset. Use INSERT ... SELECT
// so Snowflake consumes the stream rows when the statement commits.
snowflake.createStatement({
  sqlText: `
    INSERT INTO ${tempManifestTable} (workflow_name, run_id)
    SELECT DISTINCT workflow_name, run_id
    FROM ${manifestStream}
    WHERE METADATA$ACTION = 'INSERT'
  `
}).execute();

const manifests = snowflake.createStatement({
  sqlText: `SELECT workflow_name, run_id FROM ${tempManifestTable} ORDER BY workflow_name, run_id`
}).execute();

const processed = [];
while (manifests.next()) {
  const workflowName = manifests.getColumnValue(1);
  const runId = manifests.getColumnValue(2);

  snowflake.createStatement({
    sqlText: `CALL ${sourceLoadProcedure}(?, ?)`,
    binds: [workflowName, runId]
  }).execute();

  snowflake.createStatement({
    sqlText: `CALL ${refreshProcedure}(?, ?)`,
    binds: [workflowName, runId]
  }).execute();

  processed.push({ workflow_name: workflowName, run_id: runId });
}

return {
  status: "succeeded",
  processed_count: processed.length,
  processed_manifests: processed
};
$$;
