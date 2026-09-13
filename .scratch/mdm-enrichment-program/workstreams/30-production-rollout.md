# Production rollout

Classification: cross-cutting release workstream
Status: planned
Depends on: verified foundation and at least one verified consumer spec
Future spec: `docs/specs/mdm-enrichment/production-rollout.md`

## Destination

Each consumer moves through local fixtures, reversible dev migration, dry-run
backfill, immutable ECR image, bounded ECS/Step Functions canary, rollback proof,
and Release Owner GO without sharing release fate with another consumer.

Production rollout must use the AWS operator path, exact source and image
identities, per-run evidence, least-privilege service roles, no Terraform-owned
runtime definitions, and no schedule activation until the manual canary passes.
