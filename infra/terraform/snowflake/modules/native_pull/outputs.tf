output "storage_integration_name" {
  description = "Snowflake storage integration name."
  value       = snowflake_storage_integration_aws.native_pull.name
}

output "storage_aws_iam_user_arn" {
  description = "Snowflake-managed AWS IAM principal ARN emitted by the storage integration."
  value       = try(snowflake_storage_integration_aws.native_pull.describe_output[0].iam_user_arn, null)
}

output "storage_external_id" {
  description = "External ID configured on the Snowflake storage integration."
  value       = try(snowflake_storage_integration_aws.native_pull.describe_output[0].external_id, var.storage_external_id)
}

output "stage_fully_qualified_name" {
  description = "Fully qualified name of the export stage."
  value       = snowflake_stage_external_s3.export_stage.fully_qualified_name
}

output "manifest_pipe_notification_channel" {
  description = "Snowflake-managed SQS notification channel backing the manifest pipe."
  value       = snowflake_pipe.manifest.notification_channel
}

output "native_pull_ready" {
  description = "Whether the declarative native-pull object graph has been provisioned."
  value = (
    length(snowflake_storage_integration_aws.native_pull.describe_output) > 0
    && length(snowflake_pipe.manifest.notification_channel) > 0
    && snowflake_task.manifest_processor.started
  )
}
