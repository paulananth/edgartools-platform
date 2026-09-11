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

Resolved 2026-09-03. `.github/workflows/aws-cost-optimizer.yml` runs every
Sunday and on demand through an explicitly configured OIDC role. It uploads the
audit and plan artifacts but cannot delete. A separate protected manual apply
workflow requires a prior plan run ID and independently reviewed hash. The
workflows document exact role and authority-artifact prerequisites instead of
provisioning or broadening IAM in application code.
