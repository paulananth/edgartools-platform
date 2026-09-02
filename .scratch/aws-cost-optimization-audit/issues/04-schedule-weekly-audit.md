# Schedule the Weekly Cost Audit

Type: task
Status: resolved
Blocked by: 03

## Question

Can GitHub Actions run the audit weekly and on demand through AWS OIDC, upload
the report artifact, and surface actionable findings without storing long-lived
AWS credentials or applying remediation?

If the required OIDC role does not exist, keep the workflow fail-closed and
document the precise provisioning prerequisite rather than inventing or
silently broadening credentials.

## Answer

Resolved 2026-09-02. `.github/workflows/aws-cost-optimizer.yml` runs every
Sunday and on demand through an explicitly configured OIDC role. It uploads the
audit and plan artifacts. S3 deletion stays disabled unless the repository or
manual-run apply gate is true, and the reviewed plan is uploaded before apply.
The workflow documents its role and authority-artifact prerequisites instead
of provisioning or broadening IAM in application code.
