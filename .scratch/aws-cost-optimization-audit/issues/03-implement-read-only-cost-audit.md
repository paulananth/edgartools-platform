# Implement the Read-Only AWS Cost Audit

Type: task
Status: resolved
Blocked by: 02

## Question

Can a test-first implementation collect the approved evidence, rank S3 and
Fargate findings first, cover secondary unnecessary-cost candidates, and emit
human-readable plus JSON reports while making no mutating AWS calls?

Tests must prove threshold behavior, account/scope guards, delayed or missing
data handling, and that suggested remediation remains inert text.

## Answer

Resolved 2026-09-02. `scripts/ops/aws_cost_optimizer.py audit` validates the
AWS account, compares two closed Cost Explorer months, ranks S3 and Fargate
usage first, inventories lifecycle/versioning and the approved secondary cost
surfaces, and emits stable JSON. All AWS calls pass through a closed read-only
allowlist. Findings below the reporting thresholds remain absent unless they
represent safety or configuration drift; incomplete collection is recorded as
an explicit gap instead of being presented as a clean bill of health.
