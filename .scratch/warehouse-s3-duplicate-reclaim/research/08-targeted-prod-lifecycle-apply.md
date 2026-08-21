# Targeted prod lifecycle apply (ticket 08)

Date: 2026-08-21  
Profile: `aws-admin-prod` (same principal as `admin-user` in account `690839588395`)  
Root: `infra/terraform/accounts/prod`  
Target: `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse`  
Bucket: `edgartools-prod-warehouse-690839588395`

## Plan gate

`terraform plan -target=module.storage.aws_s3_bucket_lifecycle_configuration.warehouse`

- 0 add, 1 change, 0 destroy
- Only resource: `module.storage.aws_s3_bucket_lifecycle_configuration.warehouse` (in-place)
- No other warehouse-bucket resources in the plan (no bucket, versioning, public-access, or encryption)

## Apply

`terraform apply` of that saved plan: 0 added, 1 changed, 0 destroyed.

## Live readback

`get-bucket-lifecycle-configuration`:

| Rule ID | Prefix | Current expire | Noncurrent expire |
| --- | --- | --- | --- |
| expire-silver-staging-candidates | `warehouse/silverstage/` | 3 days | 3 days |
| expire-identity-refresh-run-snapshots | `warehouse/identity_refresh/` | 7 days | 7 days |
| expire-noncurrent-silver-canonical-versions | `warehouse/silver/` | none | 7 days |

Canonical Silver has no current-object expiration.
