# Research Safe AWS Cost-Audit Surfaces

Type: research
Status: resolved
Blocked by: none

## Question

Using current primary AWS sources, determine the read-only APIs, metrics,
pricing dimensions, data delays, IAM actions, and false-positive risks needed
for a recurring cost audit. Cover Cost Explorer; S3 current and noncurrent
storage, lifecycle, incomplete multipart uploads, and request costs;
ECS/Fargate requested CPU, memory, storage, runtime, and task-bound utilization;
and material secondary services including CloudWatch, ECR, Secrets Manager,
VPC networking, KMS, and Step Functions.

Distinguish evidence that can safely identify an Optimization Candidate from
evidence sufficient to authorize Remediation. Identify any optional AWS service
whose own recurring charge makes it unsuitable for this account-sized audit.

## Deliverable

One source-linked report at
`.scratch/aws-cost-optimization-audit/research/aws-cost-audit-surfaces-2026-09-02.md`.

## Answer

Resolved 2026-09-02. A weekly audit can stay read-only and inexpensive by using
a bounded pair of Cost Explorer queries, service metadata APIs, and existing
free telemetry. S3 deep version/multipart scans must be capped or opt-in;
Fargate findings must remain task-bound canary candidates, never profile
approvals. Do not enable paid Storage Lens advanced metrics, Container
Insights, hourly Cost Explorer, or other collectors solely for this audit.

See
[Safe AWS Cost-Audit Surfaces](../research/aws-cost-audit-surfaces-2026-09-02.md)
for the source-linked API/IAM matrix, delays, false-positive rules, telemetry
exclusions, and remediation gates.
