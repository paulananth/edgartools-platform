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
