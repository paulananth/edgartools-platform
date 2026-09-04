# Recurring AWS Cost Optimization Audit

Label: `wayfinder:map`

## Destination

Provide a weekly AWS Cost Audit that explains current spend, ranks
evidence-backed Optimization Candidates, and keeps non-S3 remediation
operator-reviewed. Focus first on S3 and ECS/Fargate, then identify material or
drifting spend in CloudWatch, ECR, Secrets Manager, VPC networking, KMS, Step
Functions, and other account services. For S3, resolve objects to an explicit
artifact-retention class and accession retention authority, then support
hash-bound deletion of exact expired versions under settled year/day rules.

## Notes

- **This map carries execution.** The user accepted the recommended safety,
  scheduling, and reporting boundaries on 2026-09-02.
- A **Cost Audit** is read-only except for the separately invoked, hash-bound
  S3 retention apply operation authorized by the user on 2026-09-02.
- An **Optimization Candidate** is evidence that spend may be avoidable; it is
  not permission to alter or delete a resource.
- **Years in active scope** controls which filing periods a consumer processes
  and supplies the cutoff for classified SEC artifact deletion. The cutoff may
  only be applied after every object in an accession bundle resolves to an
  authoritative form/date/consumer classification.
- An **Artifact Retention Class** binds an S3 bucket/prefix pattern to its date
  basis, minimum retention period, disposition (`retain`, `transition`,
  `expire`, or `review`), and protection checks.
- **Remediation** is any state-changing action. A separate manually dispatched,
  protected workflow may execute only an exact S3 VersionId deletion set from
  a prior run, bound to the independently reviewed plan hash; every other
  remediation remains guidance only.
- Report projected savings of at least USD 1/month, service spend increasing
  more than 20 percent month over month, and safety or configuration drift
  regardless of dollar value.
- The implementation must be portable for manual use and scheduled weekly by
  GitHub Actions with AWS OIDC. It must not introduce an AWS-hosted scheduler
  or runnable Terraform resource.
- Scope is AWS account `690839588395`, region `us-east-1`, with exact account
  and resource scope verified at runtime. Default inspection should be limited
  to `edgartools-*` resources unless a cost dimension cannot be attributed at
  that granularity.
- Existing findings and controls remain authoritative within their scopes:
  [Production Observability and Image Cost Control](../ops-cost-control/map.md)
  and [ECS and Step Functions Value, Cost, and Throughput Optimization](../ecs-cost-sizing/map.md).
- S3 deletion must preserve versioning, encryption, public-access protection,
  the retention plan/evidence itself, and every unexpired or unmatched bundle.
  Cross-accession deduplicated objects inherit the latest cutoff of every
  referencing filing; current or unclassified references block deletion.
- Fargate findings are task-bound candidates only. Do not recommend a profile
  promotion or downgrade without matched correctness, utilization, throughput,
  completion-time, recovery, idempotency, and cost evidence from the ECS map.
- Before implementation, use `/gof-refactor-reviewer`, then `/tdd` and
  `/code-review`. Do not force a design pattern into a small reporting tool.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- Grilling/domain-model decision — weekly GitHub Actions plus manual execution;
  read-only audit; USD 1/month opportunity threshold, 20 percent month-over-month
  drift threshold, and safety findings regardless of cost.
- [Research Safe AWS Cost-Audit Surfaces](issues/01-research-safe-aws-cost-audit-surfaces.md)
  — A bounded pair of Cost Explorer queries, service metadata, and existing free
  telemetry are sufficient; cap or opt into S3 deep scans, preserve task-bound
  Fargate gates, and do not enable paid telemetry for the audit.
- [Research the S3 Artifact-Retention Taxonomy](issues/06-research-s3-artifact-retention-taxonomy.md)
  — Seventeen grouped classes resolve to explicit days/version/run policies or
  retain/review; mixed Bronze keys require canonical accession classification,
  and 13F/proxy canonical windows currently drift from runtime defaults.
- [Design the Cost-Audit Contract and Test Seams](issues/02-design-audit-contract-and-seams.md)
  — Stable JSON evidence, pure policy functions, a strict AWS operation guard,
  and hash-bound exact-VersionId plans provide the testable public seams.
- [Implement the Read-Only AWS Cost Audit](issues/03-implement-read-only-cost-audit.md)
  — The audit ranks S3 and Fargate first, inventories secondary AWS cost
  surfaces, and keeps all non-S3 findings advisory.
- [Schedule the Weekly Cost Audit](issues/04-schedule-weekly-audit.md)
  — Weekly audit/plan and separate protected manual apply workflows use OIDC;
  apply consumes a prior persisted artifact plus its reviewed hash.
- [Verify the Cost Audit End to End](issues/05-verify-audit-end-to-end.md)
  — Focused and full tests pass; the live read-only audit completed against the
  intended account with no collection gaps and no resource mutations.
- [Decide the S3 Deletion Boundary](issues/07-decide-s3-deletion-boundary.md)
  — Classified complete filing bundles expire at canonical 2/3/5-year cutoffs;
  apply requires an unchanged reviewed plan and exact object versions.

## Not yet specified

- Whether the repository already has an OIDC role with the required read-only
  billing and inventory permissions, or whether the workflow must remain
  documented but disabled until that role is provisioned.
- Retention periods for durable run/release/audit evidence that currently has
  no explicit year-based expiration contract.

## Out of scope

- Deleting S3 objects whose artifact class, authoritative date, consumer scope,
  bundle completeness, or exact VersionId cannot be proven.
- Automatically deleting ECR images, logs, secrets, keys, endpoints, or other
  non-S3 AWS resources.
- Automatically resizing ECS task definitions, changing Step Functions,
  stopping executions, or changing schedules and concurrency.
- Treating AWS promotional credits or Free Tier as proof that underlying usage
  is free or optimized.
- Snowflake credit optimization, non-AWS deployment paths, or redesigning the
  platform's canonical data architecture.
