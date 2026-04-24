variable "environment" {
  description = "Environment label used in comments and naming."
  type        = string
}

variable "database_name" {
  description = "Snowflake database name."
  type        = string
}

variable "source_schema_name" {
  description = "Schema containing source mirror objects."
  type        = string
}

variable "gold_schema_name" {
  description = "Schema containing gold refresh procedures and task."
  type        = string
}

variable "refresh_warehouse_name" {
  description = "Warehouse used by the manifest-processing task."
  type        = string
}

variable "storage_role_arn" {
  description = "AWS IAM role ARN Snowflake assumes for export reads."
  type        = string
}

variable "storage_external_id" {
  description = "Deterministic external ID Snowflake presents when assuming the AWS role."
  type        = string
}

variable "export_root_url" {
  description = "S3 URL prefix for Snowflake export packages, including trailing slash."
  type        = string
}

variable "manifest_sns_topic_arn" {
  description = "SNS topic ARN used by Snowpipe auto-ingest."
  type        = string
}

variable "storage_integration_name" {
  description = "Optional override for the Snowflake storage integration name."
  type        = string
  default     = null
}

variable "stage_name" {
  description = "External stage name for Snowflake export reads."
  type        = string
  default     = "EDGARTOOLS_SOURCE_EXPORT_STAGE"
}

variable "parquet_file_format_name" {
  description = "Parquet file format used for mirrored source tables."
  type        = string
  default     = "EDGARTOOLS_SOURCE_EXPORT_FILE_FORMAT"
}

variable "manifest_file_format_name" {
  description = "JSON file format used for run manifests."
  type        = string
  default     = "EDGARTOOLS_SOURCE_RUN_MANIFEST_FILE_FORMAT"
}

variable "manifest_inbox_table_name" {
  description = "Manifest inbox table name."
  type        = string
  default     = "SNOWFLAKE_RUN_MANIFEST_INBOX"
}

variable "status_table_name" {
  description = "Per-run refresh status table name."
  type        = string
  default     = "SNOWFLAKE_REFRESH_STATUS"
}

variable "manifest_pipe_name" {
  description = "Snowpipe name for manifest auto-ingest."
  type        = string
  default     = "SNOWFLAKE_RUN_MANIFEST_PIPE"
}

variable "manifest_stream_name" {
  description = "Append-only stream on the manifest inbox table."
  type        = string
  default     = "SNOWFLAKE_RUN_MANIFEST_STREAM"
}

variable "manifest_task_name" {
  description = "Triggered task that processes the manifest stream."
  type        = string
  default     = "SNOWFLAKE_RUN_MANIFEST_TASK"
}

variable "source_load_procedure_name" {
  description = "Procedure that loads source mirror tables for a single manifest."
  type        = string
  default     = "LOAD_EXPORTS_FOR_RUN"
}

variable "refresh_procedure_name" {
  description = "Procedure that refreshes the gold dynamic tables after a successful source load."
  type        = string
  default     = "REFRESH_AFTER_LOAD"
}

variable "stream_processor_procedure_name" {
  description = "Procedure that drains the manifest stream and calls the load/refresh procedures."
  type        = string
  default     = "PROCESS_RUN_MANIFEST_STREAM"
}
