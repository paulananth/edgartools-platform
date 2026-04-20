# Terraform Layout

This directory contains the AWS reference deployment for the SEC warehouse.

## Structure

```text
bootstrap-state/
accounts/
  dev/
  prod/
snowflake/
  accounts/
    dev/
    prod/
  modules/
    account_baseline/
modules/
  network_runtime/
  storage_buckets/
  storage_buckets_destroyable/
  warehouse_runtime/
```

## Apply order

1. Run `bootstrap-state` in the target account to create the Terraform state bucket.
2. Copy `backend.hcl.example` to `backend.hcl` in the target account root.
3. Run `terraform init -backend-config=backend.hcl`.
4. Set the runtime bootstrap inputs in `terraform.tfvars`:
   - `container_image`
   - `edgar_identity_value` or `edgar_identity_secret_arn`
5. Publish the warehouse image outside Terraform using the Linux-first repo policy:
   - preferred: `bash infra/scripts/publish-warehouse-image.sh --aws-region <region> --ecr-repository edgartools-<env>-warehouse --image-tag <git-sha> --mode linux`
   - CodeBuild reference buildspec: `infra/codebuild/buildspec.publish-warehouse-image.yml`
   - fallback only from this Windows workspace: `--mode crane`
6. Update `container_image` in `terraform.tfvars` to the verified digest emitted by the publish step.
7. Run `terraform plan` and `terraform apply`.
8. If Terraform created empty secret containers, populate:
   - `edgartools-<env>-edgar-identity`
   - `edgartools-<env>-runner-credentials` after `aws iam create-access-key --user-name edgartools-<env>-runner`
9. Capture the `snowflake_manifest_sns_topic_arn` output and use it when bootstrapping the Snowflake-native pull objects.

## Notes

- Terraform CLI is pinned to `1.14.7`.
- AWS provider is pinned to `6.39.0`.
- S3 backend state locking uses `use_lockfile = true`.
- Bronze and warehouse data use separate buckets.
- The repository includes a Linux-first image publish script at `infra/scripts/publish-warehouse-image.sh`.
- The repository includes a reference CodeBuild buildspec at `infra/codebuild/buildspec.publish-warehouse-image.yml`.
- Runner access keys are intentionally created outside Terraform and then stored in
  `edgartools-<env>-runner-credentials`.
- The AWS runtime no longer owns Snowflake runtime secrets or private keys.
- Snowflake import bootstrap now consumes the exported manifest SNS topic ARN rather than an AWS-held Snowflake credential.
- CI/CD automation remains outside Terraform, but release publishing should use a Linux runner and direct `buildx --push`.
- No DynamoDB, Glue, Athena, NAT gateways, or private subnets are provisioned in v1.
- `accounts/dev` is intentionally destroyable. It uses force-delete semantics for data buckets, the
  ECR repository, and the runner IAM user so `terraform destroy` can fully tear down the account root.
- `accounts/prod` is intentionally not destroyable from the account root. The protected storage
  module keeps the bronze bucket behind `prevent_destroy`.
- Snowflake baseline objects are provisioned from `infra/terraform/snowflake/` and use separate
  state keys from the AWS account roots.
