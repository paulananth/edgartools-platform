# Review and Standardize ECR Repository Configuration

Type: research
Status: open
Blocked by: none

## Question

What is the canonical ECR repository topology and configuration for each
environment, and how should Terraform, GitHub Actions, image-publish, deploy,
cleanup, and rollback evidence converge on it without deleting an unverified
legacy repository or image?

The live baseline captured 2026-08-09 in account `690839588395`, region
`us-east-1` found:

- `edgartools-prod-images` exists with 11 tagged images (~3.29 GB), mutable
  tags, scan-on-push enabled, AES256 encryption, and an untagged-only lifecycle
  rule that expires untagged images beyond 20. It has no untagged images.
- `edgartools-dev-images` exists but is empty, has no lifecycle policy, and is
  mutable with scan-on-push and AES256 enabled.
- Legacy split repositories remain: `edgartools-dev-warehouse`,
  `edgartools-dev-warehouse-deps`, `edgartools-dev-mdm`, and
  `edgartools-dev-mdm-deps`. They have no lifecycle policy; at least the
  warehouse repository held two tagged images (~596 MB) and the MDM and MDM
  dependency repositories each held one tagged image (~298 MB).
- All inspected repositories use `MUTABLE` tag policy, while the deployment
  contract treats digest tags as rollback anchors and mutable environment tags
  such as `warehouse-dev`/`mdm-prod` as moving pointers.
- Terraform defines the shared `${environment}-images` repository and an
  untagged-only lifecycle policy, while the GitHub deploy workflow still names
  `edgartools-dev-images`; the legacy split repositories are not represented by
  the current shared-repository resource.

Resolve the canonical topology, tag-mutability model, scan/encryption baseline,
lifecycle policy, legacy migration/retirement criteria, and the fail-closed
reconciliation required before cleanup. Do not treat repository age or absence
from the latest workflow as sufficient deletion evidence.
