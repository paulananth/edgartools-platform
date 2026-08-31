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
after the final review fixes and rebase, the full repository suite passes with
2,819 tests, 4 skips, and 35 subtests.

Continuation after the 2026-08-28 rebase found and closed three fail-closed
edge gaps. ECS enumeration once again queries both `RUNNING` and `STOPPED`
desired states, retains tasks whose actual state is still transitional, and
turns every `DescribeTasks.failures` entry into an audit error. Cohort recording
now verifies STS account identity and both immutable source tags before
mutation, publishes all mirror tags before committing the authoritative
ETag-guarded registry, and leaves the prior registry recoverably authoritative
if mirror publication fails. Focused coverage increased to 79 passing tests;
the continuation's branch-wide verification and review are recorded in its
follow-up commit.

The required independent review then closed the remaining destructive-path
gaps. The audit now scans every ECS cluster, fails closed on every discovered
service, and recognizes both tag- and digest-pinned references to the exact
audited repository even when the task family has an unrelated name. Automatic
invocation of the legacy ECR deletion script was removed from deployment;
cleanup requires a reviewed hash-bound plan/apply cycle. Lock release now
requires the acquiring token plus an ETag-conditional delete, while deliberate
stale-lock recovery requires `--force`; every lock mutation verifies STS
account identity before touching storage. Behavioral tests prove the apply
order (identity, lock, audit, exact-ARN retirement, INACTIVE confirmation,
repeat audit, digest deletion, owner-token release) and prove that drift in the
repeat audit aborts before deletion. Canonical plan hashing now binds the exact
registry content and remains stable across unordered AWS inventory responses;
every rollback cohort ARN is verified against its recorded digest, and partial
ECR delete responses report their successful deletions accurately. The final
focused slice passes 105 tests.

The 2026-08-30 completion review closed two final integration gaps. Exact ECR
identity now binds account, region, and repository name, so a same-named
repository in another registry cannot satisfy cohort or live-task checks. The
repository-managed `sec_platform_deployer` fallback policy now authorizes the
narrow S3 registry/lock prefixes, account-wide inventory reads, exact
task-definition deregistration, and shared-repository image operations used by
the documented plan/apply path. Duplicate missing-ARN diagnostics were removed,
and all mutating CLI handlers now enter through one account-verifying context.
Focused coverage passes with 107 tests; targeted mypy, Ruff, Python and shell
syntax, generated-policy JSON validation, and `git diff --check` pass. The full
repository suite reached 2,902 passed and 5 skipped; its eight failures are
confined to unrelated acquisition-ledger Postgres integration tests whose
current test schema lacks `source_fetch_work.captured_etag`.
