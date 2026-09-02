# Research the S3 Artifact-Retention Taxonomy

Type: research
Status: resolved
Blocked by: none

## Question

Inventory every production S3 artifact class implied by the packaged path
catalog, application code, Terraform, operator scripts, and canonical docs.
For each class, identify bucket/prefix, artifact purpose, current/noncurrent
behavior, current lifecycle, date basis, business years in active scope when
one exists, immutability/audit/rollback protections, and whether existing
evidence supports `retain`, `transition`, `expire`, or only `review`.

Explicitly distinguish the 2/3/5-year consumer lookback windows for ownership,
13F, proxy, 8-K, and ADV data from S3 retention authority. Identify derived or
ephemeral classes that are already safe to expire and gaps that require a user
policy decision. Do not change AWS or lifecycle configuration.

## Deliverable

One evidence-linked report at
`.scratch/aws-cost-optimization-audit/research/s3-artifact-retention-taxonomy-2026-09-02.md`.

## Answer

Research completed 2026-09-02:
[Production S3 Artifact-Retention Taxonomy](../research/s3-artifact-retention-taxonomy-2026-09-02.md).

Outcome: the repository supports expiration only for explicit ephemeral or
superseded classes (configured staging, identity-refresh, noncurrent canonical
Silver, 30-day export, and reviewed exact-VersionId cleanup flows). Immutable
Bronze source evidence has no settled deletion window. The 2/3/5-year consumer
lookbacks describe processing scope, not deletion authority; current code has
also narrowed 13F to three months and proxy to one year, reinforcing the need
for a separate policy decision before any year-based Bronze deletion.
