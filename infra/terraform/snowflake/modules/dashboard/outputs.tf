output "schema_name" {
  description = "Dashboard schema name."
  value       = snowflake_schema.dashboard.name
}

output "stage_qualified_name" {
  description = "Fully qualified name of the Streamlit source stage."
  value       = local.stage_fqn
}

output "streamlit_qualified_name" {
  description = "Fully qualified name of the Streamlit app."
  value       = local.streamlit_fqn
}
