# Retire Stale Prod Revisions and Add Drift Gates

Type: grilling
Status: resolved
Blocked by: 07, 23

## Question

How should deployment retire superseded prod task-definition revisions and
detect Step Functions that still point at stale revisions or image digests?
Define an immutable release manifest, active-reference audit, rollback
protection, atomic update order, and a read-only drift check. The cleanup must
fail closed when a running task, state machine, rollback cohort, or release
candidate reference cannot be resolved.

Use the live reconciliation's 458 provisional retirement candidates only as a
counting check. Generate a fresh exact-ARN manifest after the protected
rollback cohort is decided; never deregister by age, revision range, image
equality, or `latest-N`.

## Answer

Reuse the rollback-cohort registry and pure reconciliation core introduced by
the ops-cost-control work; do not create a second release manifest. The audit
now treats the registry's `current` task-definition ARNs and digests as the
authoritative release identity, resolves every Step Functions and running-task
reference against the complete ACTIVE inventory, and fails closed on missing,
dynamic, non-current, tag-pinned, cross-repository, or otherwise ambiguous
references.

Retirement is an explicit plan/apply transaction. The plan hash binds the AWS
state but not the wall-clock audit timestamp, so apply can reproduce it. Apply
deregisters only the reviewed exact ARNs, in bounded batches, verifies each ARN
is INACTIVE, and performs a fresh full reconciliation after every batch before
any reviewed ECR digest can be deleted. Deploy, cleanup, and cohort recording
share the durable S3 lock, preventing a newly registered but not-yet-wired
revision from racing cleanup. The runbook documents read-only `check`, plan,
apply, operator identity, lock recovery, and the required ordering.
Images pushed after the current cohort's verified timestamp are protected as
release candidates until a later verified cohort advances that watermark,
closing the standalone publish-to-deploy window. Every cohort's immutable
source tag and exact repository are resolved alongside its rollback mirror.

A read-only production check on 2026-08-28 enumerated 18 state machines and
849 ACTIVE task definitions across eight exact families. It found zero
reference-drift findings and 836 fresh exact-ARN stale candidates; the earlier
458 value is therefore only a historical counting check. The plan correctly
refused to become appliable and produced no ECR deletion candidates because
the durable registry contains only one of the three required verified cohorts.
No production resources were changed. Record two more verified cohorts before
reviewing a fresh plan; never apply the current blocked plan.

Verification: focused audit, registry, CLI, and deploy-safety tests pass; mypy,
Python compilation, shell syntax, Ruff, and `git diff --check` pass. The broader
unit and architecture suite passes with 1,457 tests, 4 skips, and 35 subtests;
the final full repository suite passes with 2,731 tests, 4 skips, and 35
subtests.
