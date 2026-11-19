variable "organization_name" { type = string }
variable "account_name" { type = string }
variable "access_admin_user" { type = string }
variable "access_admin_role" { type = string }
variable "access_admin_private_key_file" { type = string }

variable "log_reader_public_key" {
  type        = string
  description = "Public key (no header lines) of the log reader's key pair"
}
variable "auditor_public_key" {
  type        = string
  description = "Public key (no header lines) of the auditor's key pair"
}
variable "gold_writer_public_key" {
  type        = string
  description = "Public key (no header lines) of the Gold writer's key pair (dbt)"
}
variable "mirror_databases" {
  type        = list(string)
  default     = []
  description = "The mirror target databases, once approved and created: the Gold writer reads them and nothing else outside its own schema"
}
variable "warehouse" {
  type    = string
  default = "COMPUTE_WH"
}
variable "monthly_credit_quota" {
  type    = number
  default = 10
}
variable "account_statement_timeout_seconds" {
  type    = number
  default = 7200
}
variable "service_statement_timeout_seconds" {
  type    = number
  default = 600
}
