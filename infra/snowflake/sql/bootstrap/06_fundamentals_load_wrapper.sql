-- Composite-key load wrapper for Branch B passthrough fundamentals tables.
--
-- Required session variables (same as 03_source_load_wrapper.sql):
--   set database_name = 'EDGARTOOLS_DEV';
--   set source_schema_name = 'EDGARTOOLS_SOURCE';
--   set deployer_role_name = 'EDGARTOOLS_DEV_DEPLOYER';
--   set fundamentals_load_procedure_name = 'LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN';
--
-- Why a separate proc (Q7-7b decision):
-- ------------------------------------
-- The existing LOAD_EXPORTS_FOR_RUN proc (file 03) assumes a single scalar
-- merge key per table (e.g. FACT_KEY).  The 3 fundamentals passthrough tables
-- have composite natural keys:
--   SEC_FINANCIAL_FACT      → (CIK, ACCESSION_NUMBER, CONCEPT, FISCAL_PERIOD, SEGMENT, PERIOD_END, PERIOD_START)
--   SEC_THIRTEENF_HOLDING   → (CIK, ACCESSION_NUMBER, HOLDING_INDEX)
--   SEC_FINANCIAL_DERIVED   → (CIK, ACCESSION_NUMBER, FISCAL_PERIOD)
--
-- Keeping a separate proc preserves the working Branch A code path untouched
-- (zero regression risk) and isolates Branch B failure modes per AD-13.
-- Both procs share the same status table, manifest inbox, parquet stage, and
-- file format — only the MERGE generator differs.

USE ROLE IDENTIFIER($deployer_role_name);
USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($source_schema_name);

CREATE OR REPLACE PROCEDURE IDENTIFIER($fundamentals_load_procedure_name)(workflow_name STRING, run_id STRING)
RETURNS VARIANT
LANGUAGE JAVASCRIPT
EXECUTE AS OWNER
AS
$$
const currentDatabase = snowflake.createStatement({sqlText: "SELECT CURRENT_DATABASE()"}).execute();
currentDatabase.next();
const databaseName = currentDatabase.getColumnValue(1);
const sourceSchema = "EDGARTOOLS_SOURCE";
const statusTable = `${databaseName}.${sourceSchema}.SNOWFLAKE_REFRESH_STATUS`;
const manifestInboxTable = `${databaseName}.${sourceSchema}.SNOWFLAKE_RUN_MANIFEST_INBOX`;
const parquetStage = `${databaseName}.${sourceSchema}.EDGARTOOLS_SOURCE_EXPORT_STAGE`;
const parquetFileFormat = `${databaseName}.${sourceSchema}.EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT`;

const targetTables = {
  SEC_FINANCIAL_FACT:     `${databaseName}.${sourceSchema}.SEC_FINANCIAL_FACT`,
  SEC_THIRTEENF_HOLDING:  `${databaseName}.${sourceSchema}.SEC_THIRTEENF_HOLDING`,
  SEC_FINANCIAL_DERIVED:  `${databaseName}.${sourceSchema}.SEC_FINANCIAL_DERIVED`
};

// Q4-A: hardcoded composite merge keys.  Each array lists the column names
// that together identify a row.  MERGE ON joins them with AND.
const mergeKeys = {
  SEC_FINANCIAL_FACT:     ["CIK", "ACCESSION_NUMBER", "CONCEPT", "FISCAL_PERIOD", "SEGMENT", "PERIOD_END", "PERIOD_START"],
  SEC_THIRTEENF_HOLDING:  ["CIK", "ACCESSION_NUMBER", "HOLDING_INDEX"],
  SEC_FINANCIAL_DERIVED:  ["CIK", "ACCESSION_NUMBER", "FISCAL_PERIOD"]
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
        CURRENT_TIMESTAMP() AS last_successful_refresh_at,
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
      last_successful_refresh_at = CASE
        WHEN source.source_load_status = 'succeeded' THEN source.last_successful_refresh_at
        ELSE target.last_successful_refresh_at
      END,
      updated_at = source.updated_at
    WHEN NOT MATCHED THEN INSERT (
      environment, source_workflow, run_id, business_date, manifest_completed_at,
      source_load_status, refresh_status, status,
      source_row_count, tables_loaded, error_message,
      last_successful_refresh_at, updated_at
    ) VALUES (
      source.environment, source.source_workflow, source.run_id,
      source.business_date, source.manifest_completed_at,
      source.source_load_status, source.refresh_status, source.status,
      source.source_row_count, source.tables_loaded, source.error_message,
      source.last_successful_refresh_at, source.updated_at
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

// Filter to only the fundamentals passthrough tables — this proc ignores
// dimensional / Branch A tables (those are handled by LOAD_EXPORTS_FOR_RUN).
const fundamentalsTables = tables.filter(t => targetTables.hasOwnProperty(String(t.table_name || "").toUpperCase()));

if (fundamentalsTables.length === 0) {
  return {
    status: "no_fundamentals_tables",
    workflow_name: WORKFLOW_NAME,
    run_id: RUN_ID,
    available_tables: tables.map(t => t.table_name)
  };
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
  for (const tableSpec of fundamentalsTables) {
    const tableName = String(tableSpec.table_name || "").toUpperCase();
    const targetTable = targetTables[tableName];
    if (!targetTable) {
      throw new Error(`Unsupported source table ${tableName} in run manifest.`);
    }
    const tempTableName = `TMP_FUND_${tableName}`;
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
    const keyCols = mergeKeys[staged.tableName];
    if (!keyCols || keyCols.length === 0) {
      throw new Error(`No composite merge keys defined for table ${staged.tableName}`);
    }
    const columns = getColumns(staged.tableName);
    if (columns.length === 0) {
      throw new Error(`No columns found for table ${staged.tableName}`);
    }

    // Build MERGE ON clause: target.K1 = source.K1 AND target.K2 = source.K2 ...
    const onClause = keyCols.map(c => `target.${c} = source.${c}`).join(" AND ");

    // Update non-key columns on match
    const nonKeyColumns = columns.filter(c => !keyCols.includes(c));
    const updateSet = nonKeyColumns.map(c => `${c} = source.${c}`).join(", ");
    const insertCols = columns.join(", ");
    const insertVals = columns.map(c => `source.${c}`).join(", ");

    exec(`
      MERGE INTO ${staged.targetTable} AS target
      USING ${staged.tempTableName} AS source
      ON ${onClause}
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
    environment: environmentName,
    business_date: businessDate,
    tables_loaded: stagedTables.length,
    source_row_count: totalRows,
    proc: "LOAD_FUNDAMENTALS_EXPORTS_FOR_RUN"
  };
} catch (error) {
  try {
    exec("ROLLBACK");
  } catch (rollbackError) {
    // Ignore rollback failures when no transaction is active.
  }

  upsertStatus(
    environmentName,
    businessDate,
    manifestCompletedAt,
    "failed",
    "pending",
    "failed",
    null,
    null,
    error.message
  );

  throw error;
}
$$;
