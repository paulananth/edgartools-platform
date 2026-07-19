# Canonical production promotion runbook

> **EXECUTED 2026-07-19 — this runbook is now a historical record.** The full
> prodb→prod cutover completed in one operator session: tfstate migrated to
> `edgartools-prod-tfstate-690839588395`; S3 data server-side synced into the
> canonical `-690839588395` buckets (keys preserved); `accounts/prod` state
> surgically reconciled to the committed config; IAM roles replaced with
> `sec_platform_prod_runner_*`; task defs and all state machines re-registered;
> Snowflake `EDGARTOOLS_PRODB` renamed to `EDGARTOOLS_PROD` (warehouses, roles,
> integration/stage/pipe recreated on the canonical bucket); GOLD rebuilt via
> `dbt --full-refresh`; Postgres instance renamed to `EDGARTOOLS_PROD_MDM`
> (host unchanged). See `TODOS.md` "RESOLVED (2026-07-19): prodb→prod promotion
> executed in full" and `.scratch/prodb-prod-cutover/issues/` for the evidence
> trail. `preflight-prod-promotion.sh` now checks the *post*-cutover invariants
> (canonical resources exist, no PRODB remnants); its `--allow-existing-targets`
> flag referenced below no longer exists.

This runbook promotes AWS account `690839588395` in `us-east-1` to the only production environment. It is deliberately split into checkpoints. The repository work and preflight are read-only; Terraform applies, Snowflake DDL, S3 Batch Operations jobs, credential rotation, and cleanup require a separately approved operator window.

## 1. Inventory and collision gate

Run `bash infra/scripts/preflight-prod-promotion.sh --aws-profile aws-admin-prod --aws-account-id <12-digit-id> --snow-connection edgartools-prod`. Save the output with the change record. Inventory VPC, ECS, ECR, S3, KMS, SNS, Secrets Manager, IAM roles, Step Functions, CloudWatch logs, Snowflake databases, schemas, warehouses, roles, integrations, tasks, pipes, Streamlit objects, Postgres instances, and installed Native Apps. Do not use `--allow-existing-targets` until each occupied canonical name is proven to be part of this migration.

Checkpoint A: record Terraform state backups and Snowflake object DDL; confirm no workload is writing. Roll back by making no changes and retaining the former resources.

## 2. S3 preservation

Create canonical account-suffixed buckets through the passive prod Terraform root. Build an S3 Inventory manifest for every former bronze, warehouse, and export bucket. Use S3 Batch Operations COPY jobs, preserving object metadata and encryption requirements. Versioning, encryption, and public-access blocks must remain enabled.

Validate each job's completion report, total object count, byte count, and a stratified sample of ETags/checksums. Compare Parquet readability and immutable SEC artifact keys. Run preflight with `--source-bucket` and `--expected-source-count`; note that its list count is a quick gate, while Inventory is the authoritative full count.

Checkpoint B: keep source buckets read-only and intact. Roll back runtime roots to the former buckets before accepting any new writes.

## 3. Snowflake replacement

Inventory `EDGARTOOLS_PRODB` and any pre-existing `EDGARTOOLS_PROD` collision. Rename only where Snowflake supports it and ownership is unambiguous; otherwise provision `EDGARTOOLS_PROD` with the maintained stack and migrate data using zero-copy clones or controlled `INSERT ... SELECT` operations. Recreate and validate `EDGARTOOLS_PROD_{DEPLOYER,REFRESHER,READER}`, refresh/reader warehouses, storage integration, stage, pipe, stream, procedures, tasks, and grants against canonical S3 URLs.

Create or migrate the Snowflake Postgres instance `EDGARTOOLS_PROD_MDM`; use `bootstrap-prod-mdm.sh` for database migration, role ownership, credential rotation, and AWS secret writes. Parameterize the Neo4j Native App grants with `database=EDGARTOOLS_PROD`, verify application callbacks/compute pools, and migrate graph schemas. Run dbt compile/run/test with `EDGARTOOLS_PROD*` environment values, then upload Streamlit with `DASHBOARD_DATABASE=EDGARTOOLS_PROD`.

Checkpoint C: retain the former database and Postgres instance without writes. Roll back application configuration, roles, and dashboard consumers before dropping any canonical replacement.

## 4. Application cutover

Confirm the EDGAR identity secret contains a name and email, both warehouse and MDM images resolve to ECR digests, and the generated `infra/aws-prod-application.json` contains only canonical bucket and role identifiers. Deploy through `deploy-aws-application.sh`; deploy Snowflake through `deploy-snowflake-stack.sh`; use the go-live wizard only with explicit per-stage approval.

Run bounded warehouse and MDM validation, native-pull validation, dbt tests, Streamlit smoke tests, Postgres connectivity/migrations/counts, and Neo4j graph verification. Confirm no unintended SEC pulls and validate manifest ingestion end to end.

Checkpoint D: require signed validation results and a monitoring window. Roll back task definitions/state machines and consumers to the checkpoint-B/C resources if validation fails.

## 5. Cleanup

Cleanup is a separate destructive change. Only after retention and rollback windows expire may operators remove `EDGARTOOLS_PRODB`, former buckets/resources, obsolete roles, warehouses, integrations, Postgres instances, Native App grants, and credentials. Re-run the preflight/inventory and confirm canonical production remains healthy before and after each deletion batch.
