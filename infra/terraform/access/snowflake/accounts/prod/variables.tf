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
variable "warehouse" {
  type    = string
  default = "COMPUTE_WH"
}
variable "account_statement_timeout_seconds" {
  type    = number
  default = 7200
}
variable "service_statement_timeout_seconds" {
  type    = number
  default = 600
}
variable "mirror_operator_public_key" {
  type        = string
  description = "The mirror operator's RSA public key, without its header lines (the private key stays in ~/.config/edgartools/mirror-operator/)"
}
variable "postgres_instance" {
  type    = string
  default = "EDGARTOOLS_PROD_MDM"
}
