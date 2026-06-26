locals {
  storage_integration_name = coalesce(var.storage_integration_name, "${var.database_name}_EXPORT_INTEGRATION")
  source_schema_fqn        = "${var.database_name}.${var.source_schema_name}"
  gold_schema_fqn          = "${var.database_name}.${var.gold_schema_name}"

  table_definitions = {
    (var.manifest_inbox_table_name) = {
      comment = "Raw run manifests auto-ingested from the Snowflake export bucket."
      columns = [
        { name = "SOURCE_FILENAME", type = "STRING", nullable = false },
        { name = "MANIFEST", type = "VARIANT", nullable = false },
        { name = "ENVIRONMENT", type = "STRING", nullable = false },
        { name = "WORKFLOW_NAME", type = "STRING", nullable = false },
        { name = "RUN_ID", type = "STRING", nullable = false },
        { name = "BUSINESS_DATE", type = "DATE", nullable = false },
        { name = "COMPLETED_AT", type = "TIMESTAMP_TZ", nullable = false },
        { name = "RECEIVED_AT", type = "TIMESTAMP_TZ", nullable = false, default_expression = "CURRENT_TIMESTAMP()" },
      ]
    }
    (var.status_table_name) = {
      comment     = "Per-run Snowflake mirror status for EdgarTools source loads and gold refreshes."
      primary_key = ["ENVIRONMENT", "SOURCE_WORKFLOW", "RUN_ID"]
      columns = [
        { name = "ENVIRONMENT", type = "STRING", nullable = false },
        { name = "SOURCE_WORKFLOW", type = "STRING", nullable = false },
        { name = "RUN_ID", type = "STRING", nullable = false },
        { name = "BUSINESS_DATE", type = "DATE", nullable = true },
        { name = "MANIFEST_COMPLETED_AT", type = "TIMESTAMP_TZ", nullable = true },
        { name = "SOURCE_LOAD_STATUS", type = "STRING", nullable = false },
        { name = "REFRESH_STATUS", type = "STRING", nullable = false },
        { name = "STATUS", type = "STRING", nullable = false },
        { name = "SOURCE_ROW_COUNT", type = "NUMBER(38,0)", nullable = true },
        { name = "TABLES_LOADED", type = "NUMBER(38,0)", nullable = true },
        { name = "ERROR_MESSAGE", type = "STRING", nullable = true },
        { name = "LAST_SUCCESSFUL_REFRESH_AT", type = "TIMESTAMP_TZ", nullable = true },
        { name = "UPDATED_AT", type = "TIMESTAMP_TZ", nullable = false, default_expression = "CURRENT_TIMESTAMP()" },
      ]
    }
    COMPANY = {
      comment = "Current company dimension mirrored from the canonical warehouse gold export."
      columns = [
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "ENTITY_NAME", type = "STRING" },
        { name = "ENTITY_TYPE", type = "STRING" },
        { name = "SIC", type = "STRING" },
        { name = "SIC_DESCRIPTION", type = "STRING" },
        { name = "STATE_OF_INCORPORATION", type = "STRING" },
        { name = "FISCAL_YEAR_END", type = "STRING" },
        { name = "LAST_SYNC_RUN_ID", type = "STRING" },
      ]
    }
    FILING_ACTIVITY = {
      comment = "Current filing-activity fact mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "FILING_KEY", type = "NUMBER(38,0)" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "FORM_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "FORM", type = "STRING" },
        { name = "FILING_DATE", type = "DATE" },
        { name = "REPORT_DATE", type = "DATE" },
        { name = "IS_XBRL", type = "BOOLEAN" },
      ]
    }
    OWNERSHIP_ACTIVITY = {
      comment = "Current ownership-activity fact mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "FORM_KEY", type = "NUMBER(38,0)" },
        { name = "PARTY_KEY", type = "NUMBER(38,0)" },
        { name = "SECURITY_KEY", type = "NUMBER(38,0)" },
        { name = "OWNERSHIP_TXN_TYPE_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "OWNER_INDEX", type = "NUMBER(38,0)" },
        { name = "TXN_INDEX", type = "NUMBER(38,0)" },
        { name = "TRANSACTION_CODE", type = "STRING" },
        { name = "TRANSACTION_SHARES", type = "FLOAT" },
        { name = "TRANSACTION_PRICE", type = "FLOAT" },
        { name = "SHARES_OWNED_AFTER", type = "FLOAT" },
        { name = "IS_DERIVATIVE", type = "BOOLEAN" },
      ]
    }
    OWNERSHIP_HOLDINGS = {
      comment = "Current ownership-holdings snapshot mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "PARTY_KEY", type = "NUMBER(38,0)" },
        { name = "SECURITY_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "OWNER_INDEX", type = "NUMBER(38,0)" },
        { name = "SHARES_OWNED_AFTER", type = "FLOAT" },
        { name = "OWNERSHIP_DIRECT_INDIRECT", type = "STRING" },
      ]
    }
    ADVISER_OFFICES = {
      comment = "Current adviser-office fact mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "GEOGRAPHY_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "OFFICE_INDEX", type = "NUMBER(38,0)" },
        { name = "OFFICE_NAME", type = "STRING" },
        { name = "IS_HEADQUARTERS", type = "BOOLEAN" },
      ]
    }
    ADVISER_DISCLOSURES = {
      comment = "Current adviser-disclosure fact mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "DISCLOSURE_CATEGORY_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "EVENT_INDEX", type = "NUMBER(38,0)" },
        { name = "IS_REPORTED", type = "BOOLEAN" },
      ]
    }
    PRIVATE_FUNDS = {
      comment = "Current private-fund fact mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "PRIVATE_FUND_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "FUND_INDEX", type = "NUMBER(38,0)" },
        { name = "AUM_AMOUNT", type = "FLOAT" },
      ]
    }
    FILING_DETAIL = {
      comment = "Current filing-detail dimension mirrored from the canonical warehouse gold export."
      columns = [
        { name = "FILING_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "FORM", type = "STRING" },
        { name = "FORM_KEY", type = "NUMBER(38,0)" },
        { name = "FILING_DATE", type = "DATE" },
        { name = "DATE_KEY", type = "NUMBER(38,0)" },
        { name = "REPORT_DATE", type = "DATE" },
        { name = "IS_XBRL", type = "BOOLEAN" },
        { name = "SIZE", type = "NUMBER(38,0)" },
      ]
    }
    TICKER_REFERENCE = {
      comment = "Current ticker-reference dimension mirrored from the canonical warehouse gold export."
      columns = [
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "TICKER", type = "STRING" },
        { name = "EXCHANGE", type = "STRING" },
        { name = "LAST_SYNC_RUN_ID", type = "STRING" },
      ]
    }
    SEC_FINANCIAL_FACT = {
      comment = "XBRL us-gaap fact per (cik, accession, concept, fiscal_period, segment, period_end, period_start). Passthrough from silver sec_financial_fact."
      columns = [
        { name = "CIK", type = "NUMBER(38,0)", nullable = false },
        { name = "ACCESSION_NUMBER", type = "STRING", nullable = false },
        { name = "CONCEPT", type = "STRING", nullable = false },
        { name = "FISCAL_PERIOD", type = "STRING", nullable = false },
        { name = "SEGMENT", type = "STRING", nullable = false },
        { name = "FISCAL_YEAR", type = "NUMBER(38,0)" },
        { name = "PERIOD_END", type = "DATE" },
        { name = "PERIOD_START", type = "DATE", nullable = false },
        { name = "FORM_TYPE", type = "STRING" },
        { name = "VALUE", type = "FLOAT" },
        { name = "UNIT", type = "STRING" },
        { name = "DECIMALS", type = "NUMBER(38,0)" },
        { name = "PARSER_VERSION", type = "STRING" },
        { name = "INGESTED_AT", type = "TIMESTAMP_TZ" },
      ]
    }
    SEC_THIRTEENF_HOLDING = {
      comment = "13F INFORMATION TABLE holding per (cik, accession, holding_index). Passthrough from silver sec_thirteenf_holding."
      columns = [
        { name = "CIK", type = "NUMBER(38,0)", nullable = false },
        { name = "ACCESSION_NUMBER", type = "STRING", nullable = false },
        { name = "HOLDING_INDEX", type = "NUMBER(38,0)", nullable = false },
        { name = "PERIOD_OF_REPORT", type = "DATE" },
        { name = "CUSIP", type = "STRING" },
        { name = "ISSUER_NAME", type = "STRING" },
        { name = "SECURITY_TITLE", type = "STRING" },
        { name = "SHARES_HELD", type = "FLOAT" },
        { name = "MARKET_VALUE", type = "FLOAT" },
        { name = "SECURITY_CLASS", type = "STRING" },
        { name = "PUT_CALL", type = "STRING" },
        { name = "DISCRETION_TYPE", type = "STRING" },
        { name = "VOTING_AUTH_SOLE", type = "FLOAT" },
        { name = "VOTING_AUTH_SHARED", type = "FLOAT" },
        { name = "VOTING_AUTH_NONE", type = "FLOAT" },
        { name = "PARSER_VERSION", type = "STRING" },
        { name = "INGESTED_AT", type = "TIMESTAMP_TZ" },
      ]
    }
    SEC_FINANCIAL_DERIVED = {
      comment = "Derived per-period financial metrics. Passthrough from silver sec_financial_derived."
      columns = [
        { name = "CIK", type = "NUMBER(38,0)", nullable = false },
        { name = "ACCESSION_NUMBER", type = "STRING", nullable = false },
        { name = "FISCAL_PERIOD", type = "STRING", nullable = false },
        { name = "FISCAL_YEAR", type = "NUMBER(38,0)" },
        { name = "PERIOD_END", type = "DATE" },
        { name = "FORM_TYPE", type = "STRING" },
        { name = "REVENUE", type = "FLOAT" },
        { name = "GROSS_PROFIT", type = "FLOAT" },
        { name = "EBITDA", type = "FLOAT" },
        { name = "EBIT", type = "FLOAT" },
        { name = "NET_INCOME", type = "FLOAT" },
        { name = "EPS_DILUTED", type = "FLOAT" },
        { name = "TOTAL_ASSETS", type = "FLOAT" },
        { name = "TOTAL_LIABILITIES", type = "FLOAT" },
        { name = "TOTAL_EQUITY", type = "FLOAT" },
        { name = "CASH_AND_EQUIVALENTS", type = "FLOAT" },
        { name = "TOTAL_DEBT", type = "FLOAT" },
        { name = "CURRENT_ASSETS", type = "FLOAT" },
        { name = "CURRENT_LIABILITIES", type = "FLOAT" },
        { name = "ACCOUNTS_RECEIVABLE", type = "FLOAT" },
        { name = "INVENTORY", type = "FLOAT" },
        { name = "SELLING_GENERAL_ADMIN_EXPENSE", type = "FLOAT" },
        { name = "RETAINED_EARNINGS", type = "FLOAT" },
        { name = "DEPRECIATION_AMORTIZATION", type = "FLOAT" },
        { name = "PROPERTY_PLANT_EQUIPMENT_NET", type = "FLOAT" },
        { name = "SHARES_OUTSTANDING", type = "FLOAT" },
        { name = "OPERATING_CASH_FLOW", type = "FLOAT" },
        { name = "CAPEX", type = "FLOAT" },
        { name = "FREE_CASH_FLOW", type = "FLOAT" },
        { name = "GROSS_MARGIN", type = "FLOAT" },
        { name = "EBITDA_MARGIN", type = "FLOAT" },
        { name = "NET_MARGIN", type = "FLOAT" },
        { name = "ROIC", type = "FLOAT" },
        { name = "ROE", type = "FLOAT" },
        { name = "ROA", type = "FLOAT" },
        { name = "PARSER_VERSION", type = "STRING" },
        { name = "INGESTED_AT", type = "TIMESTAMP_TZ" },
      ]
    }
    EARNINGS_RELEASE = {
      comment = "8-K earnings release fact per (cik, accession)."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)", nullable = false },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "FILING_DATE_KEY", type = "NUMBER(38,0)" },
        { name = "PERIOD_END_DATE_KEY", type = "NUMBER(38,0)" },
        { name = "FORM_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "FILING_DATE", type = "DATE" },
        { name = "FISCAL_YEAR", type = "NUMBER(38,0)" },
        { name = "FISCAL_QUARTER", type = "NUMBER(38,0)" },
        { name = "PERIOD_END", type = "DATE" },
        { name = "REVENUE_GAAP", type = "FLOAT" },
        { name = "NET_INCOME_GAAP", type = "FLOAT" },
        { name = "EPS_GAAP_DILUTED", type = "FLOAT" },
        { name = "HAS_NON_GAAP", type = "BOOLEAN" },
        { name = "HAS_GUIDANCE", type = "BOOLEAN" },
        { name = "PARSER_VERSION", type = "STRING" },
        { name = "INGESTED_AT", type = "TIMESTAMP_TZ" },
      ]
    }
    EXECUTIVE_RECORD = {
      comment = "DEF 14A executive compensation fact per (cik, accession, exec_name)."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)", nullable = false },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "FISCAL_YEAR_DATE_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "FISCAL_YEAR", type = "NUMBER(38,0)" },
        { name = "EXEC_NAME", type = "STRING" },
        { name = "EXEC_ROLE", type = "STRING" },
        { name = "TOTAL_COMP", type = "FLOAT" },
        { name = "BASE_SALARY", type = "FLOAT" },
        { name = "BONUS", type = "FLOAT" },
        { name = "STOCK_AWARDS", type = "FLOAT" },
        { name = "OPTION_AWARDS", type = "FLOAT" },
        { name = "NON_EQUITY_INCENTIVE", type = "FLOAT" },
        { name = "PARSER_VERSION", type = "STRING" },
        { name = "INGESTED_AT", type = "TIMESTAMP_TZ" },
      ]
    }
    ACCOUNTING_FLAG = {
      comment = "10-K accounting flag fact per (cik, accession)."
      columns = [
        { name = "FACT_KEY", type = "NUMBER(38,0)", nullable = false },
        { name = "COMPANY_KEY", type = "NUMBER(38,0)" },
        { name = "FISCAL_YEAR_DATE_KEY", type = "NUMBER(38,0)" },
        { name = "FORM_KEY", type = "NUMBER(38,0)" },
        { name = "ACCESSION_NUMBER", type = "STRING" },
        { name = "CIK", type = "NUMBER(38,0)" },
        { name = "FISCAL_YEAR", type = "NUMBER(38,0)" },
        { name = "PERIOD_END", type = "DATE" },
        { name = "FORM_TYPE", type = "STRING" },
        { name = "AUDITOR_NAME", type = "STRING" },
        { name = "AUDITOR_PCAOB_ID", type = "STRING" },
        { name = "AUDITOR_LOCATION", type = "STRING" },
        { name = "ICFR_ATTESTATION", type = "BOOLEAN" },
        { name = "AUDITOR_CHANGED", type = "BOOLEAN" },
        { name = "BENEISH_M_SCORE", type = "FLOAT" },
        { name = "ALTMAN_Z_SCORE", type = "FLOAT" },
        { name = "PIOTROSKI_F_SCORE", type = "NUMBER(38,0)" },
        { name = "PARSER_VERSION", type = "STRING" },
        { name = "INGESTED_AT", type = "TIMESTAMP_TZ" },
      ]
    }
  }

  manifest_copy_statement = trimspace(<<-SQL
    COPY INTO ${snowflake_table.tables[var.manifest_inbox_table_name].fully_qualified_name}
      (SOURCE_FILENAME, MANIFEST, ENVIRONMENT, WORKFLOW_NAME, RUN_ID, BUSINESS_DATE, COMPLETED_AT)
    FROM (
      SELECT
        METADATA$FILENAME,
        $1,
        $1:environment::STRING,
        $1:workflow_name::STRING,
        $1:run_id::STRING,
        TO_DATE($1:business_date::STRING),
        TO_TIMESTAMP_TZ($1:completed_at::STRING)
      FROM @${snowflake_stage_external_s3.export_stage.fully_qualified_name}/manifests/
    )
    FILE_FORMAT = (FORMAT_NAME = ${snowflake_file_format.manifest.fully_qualified_name})
    PATTERN = '.*run_manifest\\.json'
  SQL
  )

  source_load_procedure_sql = replace(
    replace(
      replace(
        replace(
          replace(
            replace(file("${path.module}/sql/source_load_procedure.sql"), "__SOURCE_LOAD_PROCEDURE_NAME__", "${local.source_schema_fqn}.${var.source_load_procedure_name}"),
            "__SOURCE_SCHEMA__",
            var.source_schema_name,
          ),
          "__STATUS_TABLE_NAME__",
          var.status_table_name,
        ),
        "__MANIFEST_INBOX_TABLE_NAME__",
        var.manifest_inbox_table_name,
      ),
      "__STAGE_NAME__",
      var.stage_name,
    ),
    "__PARQUET_FILE_FORMAT_NAME__",
    var.parquet_file_format_name,
  )

  refresh_procedure_sql = replace(
    replace(
      replace(
        replace(file("${path.module}/sql/refresh_procedure.sql"), "__SOURCE_SCHEMA__", var.source_schema_name),
        "__GOLD_SCHEMA__",
        var.gold_schema_name,
      ),
      "__STATUS_TABLE_NAME__",
      var.status_table_name,
    ),
    "__REFRESH_PROCEDURE_NAME__",
    "${local.gold_schema_fqn}.${var.refresh_procedure_name}",
  )

  stream_processor_procedure_sql = replace(
    replace(
      replace(
        replace(
          replace(
            replace(file("${path.module}/sql/stream_processor_procedure.sql"), "__SOURCE_SCHEMA__", var.source_schema_name),
            "__MANIFEST_STREAM_NAME__",
            var.manifest_stream_name,
          ),
          "__SOURCE_LOAD_PROCEDURE_NAME__",
          var.source_load_procedure_name,
        ),
        "__GOLD_SCHEMA__",
        var.gold_schema_name,
      ),
      "__REFRESH_PROCEDURE_NAME__",
      var.refresh_procedure_name,
    ),
    "__STREAM_PROCESSOR_PROCEDURE_NAME__",
    "${local.gold_schema_fqn}.${var.stream_processor_procedure_name}",
  )
}

resource "snowflake_storage_integration_aws" "native_pull" {
  name                      = local.storage_integration_name
  enabled                   = true
  storage_provider          = "S3"
  storage_allowed_locations = [var.export_root_url]
  storage_aws_role_arn      = var.storage_role_arn
  storage_aws_external_id   = var.storage_external_id
  comment                   = "EdgarTools native-pull storage integration for ${var.environment}."
}

resource "snowflake_file_format" "parquet" {
  database    = var.database_name
  schema      = var.source_schema_name
  name        = var.parquet_file_format_name
  format_type = "PARQUET"
  compression = "AUTO"
  comment     = "Parquet file format for EdgarTools Snowflake-native source mirrors."
}

resource "snowflake_file_format" "manifest" {
  database          = var.database_name
  schema            = var.source_schema_name
  name              = var.manifest_file_format_name
  format_type       = "JSON"
  compression       = "AUTO"
  strip_outer_array = false
  comment           = "JSON file format for EdgarTools Snowflake run manifests."
}

resource "snowflake_stage_external_s3" "export_stage" {
  database            = var.database_name
  schema              = var.source_schema_name
  name                = var.stage_name
  url                 = var.export_root_url
  storage_integration = snowflake_storage_integration_aws.native_pull.name
  comment             = "EdgarTools export stage used for Snowflake-native pull ingestion."
}

resource "snowflake_table" "tables" {
  for_each = local.table_definitions

  database = var.database_name
  schema   = var.source_schema_name
  name     = each.key
  comment  = each.value.comment
  # CHANGE_TRACKING must be true on every source table: the manifest_inbox
  # has a stream over it, and every gold dynamic table consumes the source
  # tables incrementally — both paths fail with "Change tracking is not
  # enabled or has been missing for the time range requested" otherwise.
  change_tracking = true

  dynamic "column" {
    for_each = each.value.columns
    content {
      name     = column.value.name
      type     = column.value.type
      nullable = lookup(column.value, "nullable", true)

      dynamic "default" {
        for_each = lookup(column.value, "default_expression", null) == null ? [] : [column.value.default_expression]
        content {
          expression = default.value
        }
      }
    }
  }

  dynamic "primary_key" {
    for_each = lookup(each.value, "primary_key", null) == null ? [] : [each.value.primary_key]
    content {
      keys = primary_key.value
    }
  }
}

resource "snowflake_pipe" "manifest" {
  database          = var.database_name
  schema            = var.source_schema_name
  name              = var.manifest_pipe_name
  auto_ingest       = true
  aws_sns_topic_arn = var.manifest_sns_topic_arn
  comment           = "Snowpipe auto-ingest for EdgarTools run manifests."
  copy_statement    = local.manifest_copy_statement

  lifecycle {
    replace_triggered_by = [
      snowflake_stage_external_s3.export_stage.url,
      snowflake_stage_external_s3.export_stage.storage_integration,
    ]
  }
}

resource "snowflake_stream_on_table" "manifest" {
  database    = var.database_name
  schema      = var.source_schema_name
  name        = var.manifest_stream_name
  table       = snowflake_table.tables[var.manifest_inbox_table_name].fully_qualified_name
  append_only = "true"
  comment     = "Append-only stream over EdgarTools manifest inbox rows."
}

resource "snowflake_execute" "source_load_procedure" {
  execute = local.source_load_procedure_sql
  query   = "SHOW PROCEDURES LIKE '${var.source_load_procedure_name}' IN SCHEMA ${local.source_schema_fqn}"
  revert  = "DROP PROCEDURE IF EXISTS ${local.source_schema_fqn}.${var.source_load_procedure_name}(VARCHAR, VARCHAR)"

  depends_on = [
    snowflake_stage_external_s3.export_stage,
    snowflake_file_format.parquet,
    snowflake_table.tables,
  ]
}

resource "snowflake_execute" "refresh_procedure" {
  execute = local.refresh_procedure_sql
  query   = "SHOW PROCEDURES LIKE '${var.refresh_procedure_name}' IN SCHEMA ${local.gold_schema_fqn}"
  revert  = "DROP PROCEDURE IF EXISTS ${local.gold_schema_fqn}.${var.refresh_procedure_name}(VARCHAR, VARCHAR)"

  depends_on = [
    snowflake_table.tables,
  ]
}

resource "snowflake_execute" "stream_processor_procedure" {
  execute = local.stream_processor_procedure_sql
  query   = "SHOW PROCEDURES LIKE '${var.stream_processor_procedure_name}' IN SCHEMA ${local.gold_schema_fqn}"
  revert  = "DROP PROCEDURE IF EXISTS ${local.gold_schema_fqn}.${var.stream_processor_procedure_name}()"

  depends_on = [
    snowflake_stream_on_table.manifest,
    snowflake_execute.source_load_procedure,
    snowflake_execute.refresh_procedure,
  ]
}

resource "snowflake_task" "manifest_processor" {
  database      = var.database_name
  schema        = var.gold_schema_name
  name          = var.manifest_task_name
  warehouse     = var.refresh_warehouse_name
  started       = true
  when          = "SYSTEM$STREAM_HAS_DATA('${snowflake_stream_on_table.manifest.fully_qualified_name}')"
  sql_statement = "CALL ${local.gold_schema_fqn}.${var.stream_processor_procedure_name}()"
  comment       = "Triggered task that processes EdgarTools manifest stream rows."

  depends_on = [
    snowflake_execute.stream_processor_procedure,
  ]
}
