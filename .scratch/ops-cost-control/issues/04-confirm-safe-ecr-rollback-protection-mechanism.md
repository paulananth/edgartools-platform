# Confirm a Safe ECR Rollback-Protection Mechanism

Type: research
Status: resolved
Blocked by: none

## Question

What exact ECR lifecycle, digest-tagging, ECS task-definition retirement, and
pre-deletion audit mechanism can retain the Rollback Image Set while allowing
older tagged images to expire safely?

Use current authoritative AWS behavior to determine lifecycle rule semantics,
tag-prefix/count interactions, whether ECS references protect images
automatically, how to enumerate running-task digests, how deployment cohorts
identify the current plus two verified rollback digests, and how a dry-run
proves no candidate is referenced. The result must fail closed on missing or
ambiguous rollback evidence.

## Answer

Use the hybrid, fail-closed contract documented in
[Safe ECR Rollback Protection](../research/safe-ecr-rollback-protection.md).

ECR lifecycle rules cannot identify verified deployments or ECS references and
must not expire tagged final runtime images by age or repository count. Keep a
durable three-cohort registry (current plus two verified rollback cohorts),
mirror its slots with ECR retention tags, reconcile every active task
definition, production Step Functions definition, ECS service/deployment/task
set, and live/transitional task, and deregister stale task definitions before
their images become eligible. Delete tagged stale images only from a hash-bound
dry-run plan after a repeated just-in-time audit. Keep final-repository lifecycle
automation untagged-only; manage dependency repositories under a separate
build-cache policy.

Any missing, ambiguous, unpaginated, unresolved, or changed evidence aborts the
operation. ECR and ECS do not automatically provide the cross-service rollback
protection this cleanup requires.

**Correction (2026-08-11, caught while working ticket 05):** this research
(dated 2026-08-01) and the linked doc's "Repository scope" table assume the
pre-consolidation split — two final repos (`edgartools-prod-warehouse`,
`edgartools-prod-mdm`) plus two `-deps` repos. That split no longer exists:
CLAUDE.md's "Image management" section and
`infra/terraform/modules/warehouse_runtime/main.tf:16-22` confirm all four
image kinds now share one repository (`edgartools-prod-images`), with
role/stage encoded in the tag prefix (`warehouse-*`/`mdm-*`/`warehouse-deps-*`/
`mdm-deps-*`) instead of the repository name. The hybrid contract's
*mechanism* (durable cohort registry, ECR mirror tags, ECS/Step Functions
reconciliation, fail-closed conditions) is unaffected by this — only the
"repository scope" framing needs to shift from per-repository to
per-tag-prefix within the single shared repo. Not re-litigated here; ticket
05 carries the corrected scope forward.
