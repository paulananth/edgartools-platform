# Define the AWS-side precondition contract this script requires

Type: task
Status: resolved

## Question

The map's Destination puts AWS-side provisioning (S3 buckets, IAM trust
role for the storage integration, SNS topic for manifest events, the
Step Functions/ECS compute that runs the warehouse ETL) out of scope — it's
a documented precondition, not something this script builds. But "documented
precondition" doesn't exist yet as an actual document; today those values
are only implicit in `infra/terraform/snowflake/accounts/dev/terraform.tfvars`
(`snowflake_storage_role_arn`, `snowflake_export_root_url`,
`snowflake_manifest_sns_topic_arn`) and the AWS-side Terraform roots that
produce them (`infra/terraform/accounts/{dev,prod}`).

Resolve by writing down (as this ticket's answer, or a linked doc): the
exact list of AWS resources/ARNs/names this Snowflake-provisioning script
requires to already exist before it can run, in what naming pattern, and
which existing AWS Terraform module/output produces each one — so the
Snowflake-side script has a fixed, checkable parameter contract to code
against (e.g. "fail fast with a clear message if `snowflake_storage_role_arn`
doesn't resolve to a real IAM role" rather than a confusing Terraform plan
error).

Not blocked on Ticket 01 (Terraform structure) — this is about the AWS
resource contract itself, which holds regardless of how the Snowflake-side
Terraform roots end up organized.

## Answer

Traced live, not assumed — every value below was confirmed by reading the
actual Terraform source (not just prod's `terraform.tfvars`), and prod's
`access/aws/accounts/prod` root already exposes all four as a single output
set (`outputs.tf`), which is the one true contract to depend on.

**The contract is 4 values, not 3** — the map's Destination text named
three (`snowflake_storage_role_arn`, `snowflake_export_root_url`,
`snowflake_manifest_sns_topic_arn`); tracing `native_pull`'s actual
`variables.tf` surfaced a 4th, `storage_external_id`, that's easy to miss
because it isn't purely AWS→Snowflake one-directional (see below).

| Value | AWS resource | Naming pattern | Produced by |
|---|---|---|---|
| `snowflake_storage_role_arn` | IAM role Snowflake assumes for S3 export reads | `${name_prefix}-snowflake-s3` (e.g. `edgartools-prod-snowflake-s3`) | `infra/terraform/access/aws/modules/runtime_access` (`main.tf:73`), invoked from `infra/terraform/access/aws/accounts/<env>/main.tf`, exposed as root output `snowflake_storage_role_arn` |
| `snowflake_manifest_sns_topic_arn` | SNS topic for Snowpipe auto-ingest / run-manifest events | `${name_prefix}-snowflake-manifest-events` | `infra/terraform/modules/warehouse_runtime` (`main.tf:72-74`), invoked from `infra/terraform/accounts/<env>/main.tf` (`module.runtime`), re-exposed by the access root as `snowflake_manifest_sns_topic_arn` |
| `snowflake_export_root_url` | S3 URL prefix for export Parquet/manifest objects | `s3://${snowflake_export_bucket_name}/warehouse/artifacts/snowflake_exports/` | `infra/terraform/modules/warehouse_runtime` (`main.tf:3-5`), which derives it from `module.storage.snowflake_export_bucket_name` (bucket itself named `edgartools-<env>-snowflake-export-<aws_account_id>` by `infra/terraform/modules/storage_buckets`) |
| `storage_external_id` | External ID the storage-role trust policy requires (`sts:ExternalId` condition, `runtime_access/main.tf:86`) | `edgartools-<env>-snowflake-native-pull` | **Set independently on both sides and must match**: the AWS root's `var.snowflake_storage_external_id` feeds the trust condition directly; the Snowflake root defaults its own `snowflake_storage_external_id` var to the same string via `coalesce(var, "edgartools-${environment}-snowflake-native-pull")` (`snowflake/accounts/prod/main.tf:13`). Neither side reads the other's Terraform state — they're coordinated by naming convention only, not a wired dependency. A new environment must keep both sides' `<env>` (or in this map's terms, `<slug>`) segment identical, or the storage integration silently fails auth. |

**Fastest way to pull the first three for a real environment:** don't
hand-copy tfvars — run `terraform output -json` against the AWS side's
`access/aws/accounts/<env>` root (all three plus the external ID are
already surfaced there as of this reading) and feed that JSON straight into
the Snowflake-side config generator from Ticket 01, rather than re-deriving
ARNs/URLs by hand or convention-guessing bucket names.

**Fail-fast check, concretely:** before `terraform plan`/`apply` on the
Snowflake side, verify each value resolves to a real object —
`aws iam get-role --role-name <parsed-from-arn>`,
`aws sns get-topic-attributes --topic-arn <arn>`, `aws s3 ls <export-root-url
with s3:// stripped>` — and fail with a clear message naming which
precondition is missing, rather than letting a bad ARN surface as an opaque
Snowflake `CREATE STORAGE INTEGRATION`/`CREATE STAGE` error deep into the
apply.

**Real, not yet closed gap this tracing surfaced:** the AWS-side roots that
produce all four values (`infra/terraform/accounts/{dev,prod}`,
`infra/terraform/access/aws/accounts/{dev,prod}`) are *themselves* still
hardcoded per-directory with a literal `environment = "prod"` / `"dev"`
string in `locals` — i.e. the AWS side has the exact same pre-Ticket-01
enum problem the Snowflake side just solved, and naming (`edgartools-<env>-*`)
won't automatically extend to an arbitrary slug like `secondary` without a
matching AWS root existing first. This is explicitly out of scope for this
map (AWS-side provisioning is a documented precondition, not built here) —
noted for whoever stands up the actual AWS side of a new environment, not
actioned in this ticket.
