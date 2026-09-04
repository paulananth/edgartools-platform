# Recurring AWS cost optimizer

`scripts/ops/aws_cost_optimizer.py` performs a weekly cost audit and enforces
classified S3 artifact retention. It does not resize Fargate tasks or mutate
CloudWatch, ECR, Secrets Manager, VPC, KMS, or Step Functions.

## Cost policy

The audit compares the two most recent complete months. It reports projected
savings of at least USD 1/month, service growth over 20 percent, and evidence
gaps. S3 and ECS/Fargate rank first. Fargate task definitions are inventory
only; rightsizing remains behind the repeated candidate/control canary gates in
`.scratch/ecs-cost-sizing/map.md`.

```bash
uv run python scripts/ops/aws_cost_optimizer.py \
  --profile aws-admin-dev \
  audit \
  --expected-account-id 690839588395 \
  --resource-prefix edgartools-prod \
  --output /tmp/aws-cost-audit.json
```

## S3 retention authority

S3 filing keys contain CIK and accession but not form or Item 5.02 identity.
The optimizer therefore requires an accession authority derived from canonical
Snowflake Silver. It applies these source windows:

| Artifact | Retention |
| --- | ---: |
| 13F-HR / 13F-HR/A | 3 years |
| DEF 14A family | 5 years |
| Forms 3, 4, and 5 | 2 years |
| Item 5.02 8-K / 8-K/A | 2 years |
| ADV / ADV amendments | current plus 2 years |

Other 8-K filings and unclassified forms do not match a deletion rule. Existing
operational rules remain day-based: Silver staging 3 days, identity-refresh and
noncurrent canonical Silver 7 days, and Snowflake exports 30 days.

Generate the authority using the checked-in read-only query:

```bash
export SNOW_CONNECTION=snowconn

snow sql \
  --connection "$SNOW_CONNECTION" \
  --format json \
  --query "$(sed '/^--/d' infra/snowflake/sql/operations/aws_cost_retention_authority.sql)" \
  > /tmp/retention-authority-snowflake.json

uv run python scripts/ops/aws_cost_optimizer.py \
  normalize-authority \
  --snowflake-json /tmp/retention-authority-snowflake.json \
  --output /tmp/retention-authority.jsonl
```

The query includes every known filing and text key, requires registered index,
primary-attachment, and projected-text evidence, and marks the accession
incomplete if an attachment lacks its registered raw object. Because raw bytes
are deduplicated across accessions, it also emits every cross-accession filing
that references an object stored under the bundle. The planner uses the latest
retention deadline across those references; a current or unclassified reference
blocks deletion. An incomplete or unmatched accession is never selected.

Publish the authority at a protected operational prefix outside every deletion
rule, for example:

```bash
aws --profile sec_platform_deployer --region us-east-1 s3 cp \
  /tmp/retention-authority.jsonl \
  s3://edgartools-prod-warehouse-690839588395/warehouse/release/aws-cost-optimizer/retention-authority.jsonl
```

## Retention plan and apply

Planning lists exact current versions, noncurrent versions, and delete markers
for each complete expired bundle. The default batch is capped at 1,000
authorities so weekly cleanup remains bounded.

```bash
uv run python scripts/ops/aws_cost_optimizer.py \
  --profile sec_platform_deployer \
  retention-plan \
  --expected-account-id 690839588395 \
  --authority-jsonl /tmp/retention-authority.jsonl \
  --max-authorities 1000 \
  --output /tmp/s3-retention-plan.json
```

Apply requires the exact reviewed plan hash and an explicit confirmation. It
re-reads every affected prefix and refuses if any VersionId, ETag, size, latest
status, or delete marker changed. It deletes only exact planned VersionIds, so
a concurrent new version cannot be deleted, and then requires each affected
prefix to be empty. A concurrent addition is preserved and reported as failed
post-apply drift.

```bash
PLAN_HASH="$(jq -r .plan_hash /tmp/s3-retention-plan.json)"

uv run python scripts/ops/aws_cost_optimizer.py \
  --profile sec_platform_deployer \
  retention-apply \
  --plan /tmp/s3-retention-plan.json \
  --plan-hash "$PLAN_HASH" \
  --confirm-delete-expired-s3 \
  --evidence-dir /tmp/s3-retention-evidence
```

## Weekly GitHub Actions configuration

`.github/workflows/aws-cost-optimizer.yml` runs Sundays at 08:17 UTC and can be
started manually. It audits and persists a plan but never deletes. Configure
these repository variables:

- `AWS_COST_OPTIMIZER_ROLE_ARN`: dedicated GitHub OIDC role.
- `AWS_COST_OPTIMIZER_RETENTION_AUTHORITY_URI`: protected S3 URI containing the
  refreshed JSONL authority.

After reviewing that artifact, manually run
`.github/workflows/aws-cost-retention-apply.yml` with the prior optimizer run ID
and its reviewed plan hash. Configure the `aws-cost-retention` GitHub environment
with required reviewers so plan creation cannot approve its own deletion.
Set `AWS_COST_RETENTION_APPLY_ROLE_ARN` in that protected environment to a
separate OIDC role; the weekly audit role must not have deletion permission.

The role needs the read-only actions listed in
`.scratch/aws-cost-optimization-audit/research/aws-cost-audit-surfaces-2026-09-02.md`.
For the separate reviewed-retention role, add only `s3:DeleteObjectVersion` on
`arn:aws:s3:::edgartools-prod-bronze-690839588395/warehouse/bronze/filings/*`
and `/warehouse/bronze/text/*`; do not grant `s3:DeleteObject`, bucket lifecycle
mutation, or deletion on the authority/evidence prefix.
The audit role also needs `s3:GetObject` only on the exact protected authority
object. If that object uses SSE-KMS, grant `kms:Decrypt` only for its key and
only through S3. The apply role needs `s3:ListBucketVersions` on the Bronze
bucket in addition to the scoped `s3:DeleteObjectVersion` permission.
