# Task Definition and Step Functions Reference Reconciliation Research

Date: 2026-08-09
Repository baseline: `96daa74ee22cf8dcd77768498bccb11762815d15` (`origin/main`)
Scope: local repository and Git history only; no AWS calls or mutations were made.

## Conclusion

The six live task definitions form a coherent two-image deployment cohort, but
the repository does not contain a durable release record proving that the exact
warehouse/MDM source pair was the approved candidate. The MDM image contains
the last MDM runtime fix on `main`; the warehouse image predates one later
warehouse-side `gold-verify-live` correction. No task-definition retirement
should proceed until the current cohort and one complete prior known-good cohort
are captured as protected sets and all 26 live state-machine definitions pass a
post-capture reference audit.

## Release cohort evidence

- The handoff baseline records all 26 production state machines referencing
  exactly six revisions: warehouse `small:166`, `medium:170`, `large:163` on
  digest `sha256:86f511...c625`, and MDM `small:143`, `medium:143`, `large:77`
  on digest `sha256:9f55a0...11de2`. It records source tags
  `warehouse-sha-e244a5712f65` and `mdm-sha-1492ec26be2e` respectively
  (`.scratch/ecs-cost-sizing/post-handoff-baseline-2026-08-09.md`).
- Both source commits are ancestors of `96daa74e`. Warehouse source
  `e244a5712f65058f280df6e8b37f3c1639b5723e` is PR #381's MDM concurrency
  fix; MDM source `1492ec26be2ec928e7a61da2356258ccfa32b5e6` is the later Wayfinder/docs
  commit after PRs #382-#386. No Git tag points at or contains either commit.
- The deploy path intentionally supports distinct warehouse and MDM digest
  references, refuses to reuse one image for both roles, and verifies each
  digest has the expected role-prefixed ECR tag
  (`infra/scripts/deploy-aws-application.sh:939-975`). Image publication
  resolves a pushed tag back to an immutable `repository@sha256:...` reference
  (`infra/scripts/publish-warehouse-image.sh:167-183`). A cohort composed from
  different role source commits is therefore supported by design.
- The exact intended cohort is not durable in Git. The application manifest and
  image-ref files are ignored (`.gitignore:81-82`) and are absent in this
  worktree. The separate release-evidence schema stores one candidate
  `commit_sha` plus two image digests, but not one source commit per role
  (`edgar_warehouse/application/release_evidence.py:49-64`,
  `edgar_warehouse/application/release_evidence.py:227-237`). No current
  `docs/release-readiness/releases/*/release-evidence.json` binds the two live
  source tags/digests. Thus the split cohort is operationally consistent, but
  local evidence alone cannot prove release approval.

## Runtime changes absent from each image

Both final Dockerfiles copy the repository's `edgar` and `edgar_warehouse`
trees into the image (`Dockerfile:4-9`, `Dockerfile.mdm-neo4j:4-9`), so commit
ancestry gives a reliable source-content comparison.

| Live role | Source commit | Runtime delta on `main` | Assessment |
| --- | --- | --- | --- |
| Warehouse | `e244a5712f65` | PR #385 (`ee62a968`) fixes `edgar_warehouse/mdm/adv_bulk.py`; PR #388 (`98adb781`) changes `edgar_warehouse/serving/gold_verify.py` so intentionally pilot-only tables do not fail `gold-verify-live`. | The MDM fix is outside the warehouse role. The `gold_verify` correction is warehouse-side source absent from this image. The install flow currently invokes `gold-verify-live` from the local checkout, not through an ECS state machine (`infra/scripts/install.sh:778-807`), so this is confirmed source drift but not proof that a live ECS workflow is broken. |
| MDM | `1492ec26be2e` | Only PR #388's `gold_verify` correction and the ECS sizing planning commit follow it. | PR #385's production MDM idempotency fix is included. No later MDM runtime code change exists on `main`; the only runtime delta belongs to the warehouse verification command. |

The intervening schema/bootstrap and operator-script changes in commits
`69c53b57`, `ae6c78ff`, and `80c3d550` are not copied by either final
Dockerfile. They matter to provisioning/operations, not container source
identity. The source history therefore supports retaining the current MDM
digest while treating the warehouse digest as behind current warehouse source.
It does not, by itself, authorize a redeploy.

## Registration and pinning behavior

- Every deploy unconditionally registers fresh warehouse and MDM task-definition
  revisions; there is no equality check or revision reuse
  (`infra/scripts/deploy-aws-application.sh:1058-1077`,
  `infra/scripts/deploy-aws-application.sh:1140-1190`). This explains revision
  accumulation and means “latest revision” is not equivalent to “validated
  release.”
- Generated Amazon States Language embeds the exact newly registered task
  definition ARN in each ECS state (`infra/scripts/deploy-aws-application.sh:1403`,
  with the profile-to-ARN mapping at
  `infra/scripts/deploy-aws-application.sh:1193-1229`). State machines are then
  created or updated in place (`infra/scripts/deploy-aws-application.sh:4333-4359`).
- The operation is not atomic: all six task definitions are registered first,
  state machines are updated sequentially, and only after those updates does
  the script write `task_definitions`, `state_machines`, and image refs to the
  output manifest (`infra/scripts/deploy-aws-application.sh:4765-4784`,
  `infra/scripts/deploy-aws-application.sh:4796-4888`). A failed deploy can
  therefore leave a mixed live cohort while the prior manifest remains stale or
  no new manifest exists.
- The deploy path never deregisters old revisions. The only repository command
  that deregisters task definitions is the complete environment teardown, which
  deregisters every active revision and then deletes inactive definitions
  (`infra/scripts/destroy-aws-complete.sh:580-612`). It is not a selective
  production-retirement mechanism.

## Existing rollback and drift controls

- The MDM cutover audit recursively extracts every `TaskDefinition` reference
  and fails when a manifest-listed state machine references an ARN outside the
  manifest task-definition set
  (`infra/scripts/audit-mdm-snowflake-postgres-cutover.py:197-208`,
  `infra/scripts/audit-mdm-snowflake-postgres-cutover.py:258-276`). It also
  fails if any manifest-listed execution is running before its cutover action
  (`infra/scripts/audit-mdm-snowflake-postgres-cutover.py:228-244`). This is a
  useful fail-closed primitive, but it is tied to the cutover manifest and is
  not invoked by ordinary deploy or cleanup.
- ECR cleanup keeps every tagged image, but its “active task images” scan reads
  only the latest active revision in each family
  (`infra/scripts/cleanup-ecr-images.sh:48-104`,
  `infra/scripts/cleanup-ecr-images.sh:135-175`). It therefore does not protect
  an older rollback digest merely because an older active task definition uses
  it. Retention currently depends on the rollback digest retaining a tag.
- The repository has a successful rollback rehearsal using
  `deploy-aws-application.sh --image-ref/--mdm-image-ref --skip-build`; it
  restored six task definitions and 26 state machines in 5m37s
  (`docs/release-readiness/rollback-rehearsal.json:1-20`). This validates the
  mechanism—redeploy prior immutable digests into newly registered revisions—
  but does not identify the prior cohort to protect now.
- Release-evidence validation is digest-bound and detects mutated/missing
  evidence (`edgar_warehouse/application/release_evidence.py:1-19`,
  `tests/application/test_release_evidence.py:431-451`), and its contract
  requires a rollback-readiness gate
  (`edgar_warehouse/application/release_evidence.py:111-122`). It is not wired
  to ECS task-definition reference reconciliation.

## Fail-closed protected-set and retirement policy

The following policy is supported by the current code/history and closes the
gaps above:

1. **Freeze an operator window.** Require zero running ECS tasks and zero
   running executions across the complete 26-state-machine inventory. If the
   inventory differs from the captured baseline, stop.
2. **Capture two complete protected cohorts.** Persist the exact six current
   task-definition ARNs, both digest refs, both role source commits, all 26
   state-machine ARNs, and hashes of their ASL definitions. Capture the same
   fields for one prior known-good rollback cohort. Do not derive either cohort
   from “latest revision” or a revision-count heuristic.
3. **Audit before mutation.** Recursively collect every live
   `TaskDefinition` reference. It must equal a member of the current six-ARN
   set; any missing state machine, family-only reference, unexpected revision,
   mixed digest, or unavailable protected image fails closed. Confirm protected
   image digests still have durable role/source tags because ECR cleanup does
   not scan all historical active revisions.
4. **Deploy as a staged transaction.** Register all six candidate revisions,
   validate their digest, CPU/memory, roles, secrets, log configuration, and
   runtime tags, and generate all 26 definitions before updating any live state
   machine. Then update the state machines. Because the current API loop is not
   atomic, record progress and treat any interruption as a failed mixed-cohort
   deployment.
5. **Post-audit or roll back.** A deployment is complete only when all 26 live
   definitions reference only the six candidate ARNs and the generated manifest
   matches live state. On any mismatch, redeploy the protected prior digest pair
   using the rehearsed `--skip-build` path and repeat the full reference audit.
   Do not retire revisions in the same change window.
6. **Generate an exact retirement manifest.** A revision is a candidate only
   when it is absent from every live state-machine definition, absent from both
   protected cohorts, not needed by a running task/execution, and its loss does
   not remove a protected image's only retention tag. The manifest must list
   exact ARNs and the evidence for each exclusion. Unknown or uninspectable
   references remain protected.
7. **Deregister only; delete later.** First deregister the reviewed candidate
   ARNs while preserving the current and prior cohorts. Verify the six current
   refs are still active and all 26 state machines are unchanged. Permanent
   deletion, including the object-specific `silver-inspect:3` and
   `silver-repair:3` families, requires a separate evidence-retention decision.

Under this policy, the baseline's 466 unreferenced active revisions are a
classification input, not an approved deregistration count. Local history can
define the guardrails, but a fresh read-only live reconciliation must produce
the exact retirement manifest.

## Live reconciliation after handoff

The main agent performed a fresh read-only audit against account
`690839588395`, region `us-east-1`, after the local-source research completed.
The audit used STS, ECS, ECR, Step Functions, EventBridge Scheduler, and
EventBridge APIs; it made no AWS mutations.

### Complete live reference surface

- 26 `edgartools-prod-*` state machines exist.
- Their current ASL definitions reference exactly the six current revisions
  below and no other task definition.
- All 26 have zero published Step Functions versions and zero aliases.
- All 26 have zero running executions.
- The ECS cluster has zero services, zero running tasks, and zero pending
  tasks. Its retained stopped-task listing contains only six post-handoff MDM
  validation tasks on current revisions, all with container exit code `0`.
- No EventBridge Scheduler schedule or EventBridge rule/target was found
  referencing an `edgartools` state machine or ECS task definition.

Completed historical executions are not treated as rollback references. The
standing operator policy is to start a new post-change execution rather than
redrive a pre-change execution; changing that policy requires a new reference
audit.

### Protected current cohort

| Role/profile | Task definition | Digest |
| --- | --- | --- |
| warehouse small | `edgartools-prod-small:166` | `sha256:86f511031d3fdf790f44d4308bb40157d97adbfd2c1b9fdcd4a9755d1e81c625` |
| warehouse medium | `edgartools-prod-medium:170` | same warehouse digest |
| warehouse large | `edgartools-prod-large:163` | same warehouse digest |
| MDM small | `edgartools-prod-mdm-small:143` | `sha256:9f55a0a7910cb55d1a88190c7642ccfc55b6c4f0210deccb956f6750c3711de2` |
| MDM medium | `edgartools-prod-mdm-medium:143` | same MDM digest |
| MDM large | `edgartools-prod-mdm-large:77` | same MDM digest |

The current digests retain immutable source tags
`warehouse-sha-e244a5712f65` and `mdm-sha-1492ec26be2e` in addition to the
mutable role-prod tags.

The 26 canonical ASL definitions were also captured by state-machine
`revisionId` and SHA-256 of canonicalized definition JSON during this audit.
A cleanup implementation must recalculate and compare those hashes immediately
before and after mutation; the hashes are evidence for this capture, not
permanent identifiers that excuse a fresh read.

### Provisional rollback cohort

The last pre-handoff live baseline identified this complete six-profile cohort:

| Role/profile | Task definition | Digest/source tag |
| --- | --- | --- |
| warehouse small | `edgartools-prod-small:159` | `sha256:a493e0d183f4bd1d5a01f46034b2250d76830206b49672b5f14d9a35080e504e` / `warehouse-sha-b64f1de5a660` |
| warehouse medium | `edgartools-prod-medium:164` | same warehouse digest |
| warehouse large | `edgartools-prod-large:157` | same warehouse digest |
| MDM small | `edgartools-prod-mdm-small:137` | `sha256:cc64ba854ee382256fe7f58381f57feadd923645507bac53cf7e0c57a4e4640a` / `mdm-sha-3f009d0af82a` |
| MDM medium | `edgartools-prod-mdm-medium:138` | same MDM digest |
| MDM large | `edgartools-prod-mdm-large:72` | same MDM digest |

These revisions remain active and both digests retain immutable ECR source
tags. They are the strongest available rollback candidate because they were
captured as the complete live cohort before handoff. They are not yet proven
to be a fully validated known-good release: no durable release manifest binds
them and the current evidence does not establish complete end-to-end success.
They therefore remain protected while a separate decision designates or
replaces the rollback cohort.

Numerically adjacent revisions are not substitutes. For example, current-minus-
one revisions are exact configuration duplicates of the current cohort, while
some other recently registered MDM revisions use staging digest
`sha256:6a38edf1c81b427f8118f8f619bf4b90dd29dbb316a450d9f7c08737c488107b`.
Revision order alone cannot identify a valid rollback release.

### One-off utility protection

`edgartools-prod-silver-inspect:3` and
`edgartools-prod-silver-repair:3` are not referenced by live orchestration.
Both embed object-version-specific commands and use immutable digest
`sha256:575aa0f762095a2577dbefe763645b2815d975570a0e4bcb1f19b711e5671ee1`
tagged `warehouse-sha-987042c6db6d`. They remain protected pending a separate
evidence-retention decision; they are not reusable production utilities.

### Classification result

There are 472 active revisions across eight prod families:

- 6 protected current revisions.
- 6 provisionally protected rollback revisions.
- 2 protected one-off utility revisions pending evidence-retention review.
- 458 provisional retirement candidates.

The 458 count is not an approved deregistration manifest. Before cleanup, the
rollback cohort must be explicitly designated, every active ARN must be
re-enumerated, and exact set subtraction must be repeated against current ASL
references, protected cohorts, live tasks/executions, aliases/versions, and
external scheduler targets. Any drift or failed read makes the candidate set
empty.

## Fail-closed update and retirement order

1. Designate and persist the current and rollback six-revision cohorts,
   immutable digest/source tags, all 26 state-machine revision IDs and ASL
   hashes, and the utility evidence-retention decision.
2. Re-read all live references and require zero tasks/executions plus exact
   equality between current ASL references and the current six-revision set.
3. Generate the candidate manifest by exact ARN set subtraction. Never select
   by revision range, age, `latest-N`, or image equality.
4. Review and sign the manifest. If any source API paginates incompletely,
   errors, or returns an unexpected family/reference, stop with zero targets.
5. Deregister only the reviewed exact ARNs in bounded batches. Do not update
   state machines or deploy images in the same change window.
6. After every batch, verify all protected revisions remain active, all 26 ASL
   hashes/references are unchanged, and no task/execution appeared. Stop on the
   first mismatch.
7. Keep deregistered definitions recoverable through AWS's inactive state and
   preserve protected ECR tags. Permanent deletion is a later operation after
   an observation window and a second reference audit.
