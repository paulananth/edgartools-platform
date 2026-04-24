CREATE OR REPLACE PROCEDURE __SOURCE_LOAD_PROCEDURE_NAME__(workflow_name STRING, run_id STRING)
RETURNS VARIANT
LANGUAGE JAVASCRIPT
EXECUTE AS OWNER
AS
$$
const currentDatabase = snowflake.createStatement({sqlText: "SELECT CURRENT_DATABASE()"}).execute();
currentDatabase.next();
const databaseName = currentDatabase.getColumnValue(1);
const sourceSchema = "__SOURCE_SCHEMA__";
const statusTable = `${databaseName}.${sourceSchema}.__STATUS_TABLE_NAME__`;
const manifestInboxTable = `${databaseName}.${sourceSchema}.__MANIFEST_INBOX_TABLE_NAME__`;
const parquetStage = `${databaseName}.${sourceSchema}.__STAGE_NAME__`;
const parquetFileFormat = `${databaseName}.${sourceSchema}.__PARQUET_FILE_FORMAT_NAME__`;

const targetTables = {
  COMPANY: `${databaseName}.${sourceSchema}.COMPANY`,
  FILING_ACTIVITY: `${databaseName}.${sourceSchema}.FILING_ACTIVITY`,
  OWNERSHIP_ACTIVITY: `${databaseName}.${sourceSchema}.OWNERSHIP_ACTIVITY`,
  OWNERSHIP_HOLDINGS: `${databaseName}.${sourceSchema}.OWNERSHIP_HOLDINGS`,
  ADVISER_OFFICES: `${databaseName}.${sourceSchema}.ADVISER_OFFICES`,
  ADVISER_DISCLOSURES: `${databaseName}.${sourceSchema}.ADVISER_DISCLOSURES`,
  PRIVATE_FUNDS: `${databaseName}.${sourceSchema}.PRIVATE_FUNDS`,
  FILING_DETAIL: `${databaseName}.${sourceSchema}.FILING_DETAIL`,
  TICKER_REFERENCE: `${databaseName}.${sourceSchema}.TICKER_REFERENCE`
};

const mergeKeys = {
  COMPANY: "COMPANY_KEY",
  FILING_ACTIVITY: "FACT_KEY",
  OWNERSHIP_ACTIVITY: "FACT_KEY",
  OWNERSHIP_HOLDINGS: "FACT_KEY",
  ADVISER_OFFICES: "FACT_KEY",
  ADVISER_DISCLOSURES: "FACT_KEY",
  PRIVATE_FUNDS: "FACT_KEY",
  FILING_DETAIL: "FILING_KEY",
  TICKER_REFERENCE: "CIK"
};

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

function upsertStatus(environmentName, businessDate, manifestCompletedAt, sourceLoadStatus, refreshStatus, status, sourceRowCount, tablesLoaded, errorMessage) {
  const errorValue = errorMessage === null || errorMessage === undefined ? "NULL" : `'${q(errorMessage)}'`;
  exec(`
    MERGE INTO ${statusTable} AS target
    USING (
      SELECT
        '${q(environmentName)}' AS environment,
        '${q(WORKFLOW_NAME)}' AS source_workflow,
        '${q(RUN_ID)}' AS run_id,
        TO_DATE('${q(businessDate)}') AS business_date,
        TO_TIMESTAMP_TZ('${q(manifestCompletedAt)}') AS manifest_completed_at,
        '${q(sourceLoadStatus)}' AS source_load_status,
        '${q(refreshStatus)}' AS refresh_status,
        '${q(status)}' AS status,
        ${sourceRowCount === null || sourceRowCount === undefined ? "NULL" : Number(sourceRowCount)} AS source_row_count,
        ${tablesLoaded === null || tablesLoaded === undefined ? "NULL" : Number(tablesLoaded)} AS tables_loaded,
        ${errorValue} AS error_message,
        CASE
          WHEN '${q(refreshStatus)}' = 'succeeded' THEN CURRENT_TIMESTAMP()
          ELSE NULL
        END AS last_successful_refresh_at,
        CURRENT_TIMESTAMP() AS updated_at
    ) AS source
    ON target.environment = source.environment
      AND target.source_workflow = source.source_workflow
      AND target.run_id = source.run_id
    WHEN MATCHED THEN UPDATE SET
      business_date = source.business_date,
      manifest_completed_at = source.manifest_completed_at,
      source_load_status = source.source_load_status,
      refresh_status = source.refresh_status,
      status = source.status,
      source_row_count = source.source_row_count,
      tables_loaded = source.tables_loaded,
      error_message = source.error_message,
      last_successful_refresh_at = COALESCE(source.last_successful_refresh_at, target.last_successful_refresh_at),
      updated_at = source.updated_at
    WHEN NOT MATCHED THEN INSERT (
      environment,
      source_workflow,
      run_id,
      business_date,
      manifest_completed_at,
      source_load_status,
      refresh_status,
      status,
      source_row_count,
      tables_loaded,
      error_message,
      last_successful_refresh_at,
      updated_at
    ) VALUES (
      source.environment,
      source.source_workflow,
      source.run_id,
      source.business_date,
      source.manifest_completed_at,
      source.source_load_status,
      source.refresh_status,
      source.status,
      source.source_row_count,
      source.tables_loaded,
      source.error_message,
      source.last_successful_refresh_at,
      source.updated_at
    )
  `);
}

const manifestRs = exec(`
  SELECT environment, workflow_name, run_id, TO_VARCHAR(business_date), TO_VARCHAR(completed_at), manifest
  FROM ${manifestInboxTable}
  WHERE workflow_name = '${q(WORKFLOW_NAME)}'
    AND run_id = '${q(RUN_ID)}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY workflow_name, run_id ORDER BY received_at DESC) = 1
`);

if (!manifestRs.next()) {
  throw new Error(`No run manifest found for workflow ${WORKFLOW_NAME} and run ${RUN_ID}.`);
}

const environmentName = manifestRs.getColumnValue(1);
const businessDate = manifestRs.getColumnValue(4);
const manifestCompletedAt = manifestRs.getColumnValue(5);
let manifest = manifestRs.getColumnValue(6);

if (typeof manifest === "string") {
  manifest = JSON.parse(manifest);
}

const tables = Array.isArray(manifest.tables) ? manifest.tables : [];
if (tables.length === 0) {
  throw new Error(`Run manifest for workflow ${WORKFLOW_NAME} and run ${RUN_ID} contains no tables.`);
}

const priorSuccess = scalar(`
  SELECT COUNT(*)
  FROM ${statusTable}
  WHERE environment = '${q(environmentName)}'
    AND source_workflow = '${q(WORKFLOW_NAME)}'
    AND run_id = '${q(RUN_ID)}'
    AND source_load_status = 'succeeded'
`);

if (Number(priorSuccess) > 0) {
  return {
    status: "already_succeeded",
    workflow_name: WORKFLOW_NAME,
    run_id: RUN_ID
  };
}

upsertStatus(environmentName, businessDate, manifestCompletedAt, "running", "pending", "running", null, null, null);

const stagedTables = [];
let totalRows = 0;

try {
  for (const tableSpec of tables) {
    const tableName = String(tableSpec.table_name || "").toUpperCase();
    const targetTable = targetTables[tableName];
    if (!targetTable) {
      throw new Error(`Unsupported source table ${tableName} in run manifest.`);
    }
    const tempTableName = `TMP_${tableName}`;
    const relativePath = String(tableSpec.relative_path || "");
    const expectedRowCount = Number(tableSpec.row_count || 0);

    exec(`CREATE OR REPLACE TEMP TABLE ${tempTableName} LIKE ${targetTable}`);
    exec(`
      COPY INTO ${tempTableName}
      FROM @${parquetStage}/${relativePath}
      FILE_FORMAT = (FORMAT_NAME = '${parquetFileFormat}')
      MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
    `);

    const loadedRowCount = Number(scalar(`SELECT COUNT(*) FROM ${tempTableName}`));
    if (loadedRowCount !== expectedRowCount) {
      throw new Error(`Row-count mismatch for ${tableName}: expected ${expectedRowCount}, loaded ${loadedRowCount}.`);
    }

    stagedTables.push({ targetTable, tempTableName, tableName, loadedRowCount });
    totalRows += loadedRowCount;
  }

  function getColumns(tableName) {
    const rs = exec(`
      SELECT COLUMN_NAME
      FROM ${databaseName}.INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = '${sourceSchema}' AND TABLE_NAME = '${tableName}'
      ORDER BY ORDINAL_POSITION
    `);
    const cols = [];
    while (rs.next()) {
      cols.push(rs.getColumnValue(1));
    }
    return cols;
  }

  exec("BEGIN");
  for (const staged of stagedTables) {
    const key = mergeKeys[staged.tableName];
    if (!key) {
      throw new Error(`No merge key defined for table ${staged.tableName}`);
    }
    const columns = getColumns(staged.tableName);
    if (columns.length === 0) {
      throw new Error(`No columns found for table ${staged.tableName}`);
    }
    const updateSet = columns.filter(c => c !== key).map(c => `${c} = source.${c}`).join(", ");
    const insertCols = columns.join(", ");
    const insertVals = columns.map(c => `source.${c}`).join(", ");

    exec(`
      MERGE INTO ${staged.targetTable} AS target
      USING ${staged.tempTableName} AS source
      ON target.${key} = source.${key}
      WHEN MATCHED THEN UPDATE SET ${updateSet}
      WHEN NOT MATCHED THEN INSERT (${insertCols}) VALUES (${insertVals})
    `);
  }
  exec("COMMIT");

  upsertStatus(
    environmentName,
    businessDate,
    manifestCompletedAt,
    "succeeded",
    "ready_for_dbt_refresh",
    "ready_for_dbt_refresh",
    totalRows,
    stagedTables.length,
    null
  );

  return {
    status: "succeeded",
    workflow_name: WORKFLOW_NAME,
    run_id: RUN_ID,
    row_count: totalRows,
    tables_loaded: stagedTables.length
  };
} catch (error) {
  exec("ROLLBACK");
  upsertStatus(
    environmentName,
    businessDate,
    manifestCompletedAt,
    "failed",
    "failed",
    "failed",
    null,
    null,
    error.message
  );
  throw error;
}
$$;
