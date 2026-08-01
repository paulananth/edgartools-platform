# Safe ECR Rollback Protection

Research date: 2026-08-01
Scope: AWS account `690839588395`, Region `us-east-1`, production repositories
`edgartools-prod-warehouse` and `edgartools-prod-mdm`

## Decision

Do not use image age or repository count as the authority for deleting tagged
production runtime images. Amazon ECR lifecycle rules have no ECS-reference
predicate, no external rollback-registry predicate, and no native `retain`
action. They match tag status/patterns and age/count, then expire matching
images. A count rule orders images by `pushed_at_time`, not by verified
deployment success. Rule priority is conflict resolution between expiration
rules, not a durable rollback registry.

Use a hybrid contract:

1. A durable **deployment-cohort registry** is authoritative for the current
   verified production cohort and the two immediately preceding verified
   cohorts. Each cohort records the warehouse and MDM image digests, immutable
   `sha-*` tags, the exact ECS task-definition ARNs, verification evidence ID,
   and verification timestamp.
2. Mirror those three cohort slots in each final ECR repository with movable
   `retain-current`, `retain-rollback-1`, and `retain-rollback-2` tags. These
   tags are assertions that must agree with the durable registry; they are not
   the sole evidence.
3. A fail-closed reconciler computes protected digests from the cohort registry,
   every `ACTIVE` task definition, every production state-machine definition,
   ECS services/deployments/task sets, and every live or transitioning ECS task.
   An image cannot be a candidate while any such reference remains.
4. Stale task-definition revisions are first proven absent from current and
   rollback cohorts, Step Functions definitions, services/deployments/task sets,
   and live tasks; they are then deregistered. Only after a repeated audit shows
   them `INACTIVE` may their image digests become candidates.
5. Tagged final-image removal is performed only from a hash-bound dry-run plan
   after a just-in-time repeat audit. The ECR lifecycle policy remains limited
   to untagged image cleanup. It must not target `sha-*`, `prod`, `retain-*`, or
   `tagStatus: any` in the final runtime repositories.

This deliberately rejects a lifecycle-only implementation. It is the smallest
mechanism that can satisfy “current + two verified rollbacks + running tasks”
without assuming ECR understands ECS or deployment success.

## Why ECR cannot infer the protected set

AWS documents lifecycle selection in terms of tag status/patterns, image count,
and time. `imageCountMoreThan` sorts by push time, and expiration rules are
applied within 24 hours after eligibility. The only documented automatic
reference protection is for a container image referenced by an ECR manifest
list; ECS task definitions and ECS tasks are not lifecycle-policy selectors.
Therefore, it is an inference from AWS's exhaustive lifecycle selection rules
that ECS references are **not** automatic ECR deletion protection. See
[How lifecycle policies work](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html)
and [lifecycle policy properties](https://docs.aws.amazon.com/AmazonECR/latest/userguide/lifecycle_policy_parameters.html).

An `ACTIVE` ECS task definition can launch tasks. Deregistration changes it to
`INACTIVE`, prevents new tasks and services from using it, and does not affect
existing tasks. ECS itself delays permanent task-definition deletion while
standalone tasks, service tasks, deployments, or task sets still depend on the
revision. That protection applies to deletion of the **task definition**, not
to deletion of its ECR image. See
[Amazon ECS task-definition states](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-definition-state.html).

Step Functions `ecs:runTask` states name a `TaskDefinition`; future executions
therefore depend on the exact task definition embedded in the active state
machine definition. `describe-state-machine` returns that Amazon States
Language definition. See
[Run ECS tasks with Step Functions](https://docs.aws.amazon.com/step-functions/latest/dg/connect-ecs.html)
and [`DescribeStateMachine`](https://docs.aws.amazon.com/step-functions/latest/APIReference/API_DescribeStateMachine.html).

## Deployment-cohort registry

The source of truth should be a versioned, encrypted, durable production control
object stored beside the platform's durable release evidence, not generated
application JSON on an operator laptop. The registry advances only after the
deployment's verification evidence is complete. Its minimum schema is:

```json
{
  "schema_version": 1,
  "account_id": "690839588395",
  "region": "us-east-1",
  "updated_at": "RFC3339 timestamp",
  "cohorts": [
    {
      "slot": "current",
      "candidate_id": "immutable release identity",
      "verified_at": "RFC3339 timestamp",
      "verification_evidence": "durable evidence reference",
      "warehouse": {
        "repository": "edgartools-prod-warehouse",
        "digest": "sha256:...",
        "immutable_tag": "sha-...",
        "task_definition_arns": ["arn:aws:ecs:...:task-definition/...:N"]
      },
      "mdm": {
        "repository": "edgartools-prod-mdm",
        "digest": "sha256:...",
        "immutable_tag": "sha-...",
        "task_definition_arns": ["arn:aws:ecs:...:task-definition/...:N"]
      }
    }
  ]
}
```

`cohorts` contains `current`, `rollback-1`, and `rollback-2`, ordered by
successful verification time, not ECR push time. A cohort is a warehouse/MDM
pair: the two roles must not be selected independently from “latest images.” If
fewer than three verified cohorts exist, retain every verified cohort and do
not prune tagged final images until the missing history is intentionally
attested. Distinct cohorts may legitimately share a digest for one role.

ECR mirror tags can be applied without pulling and pushing layers by fetching
the existing manifest and using `PutImage` with a new tag. AWS documents this
flow in [Retagging an image in Amazon ECR](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-retag.html).
The reconciler must resolve each mirror tag back to a digest and require exact
agreement with the registry before considering any deletion.

## Exact live-task enumeration

The audit must paginate every API and treat any API error, response-level
`failures` member, missing `imageDigest`, unrecognized repository URI, or
unresolved tag as a hard failure.

1. Verify `sts:GetCallerIdentity.Account == 690839588395` and Region
   `us-east-1`.
2. Paginate `ecs:ListClusters`; do not assume the named warehouse cluster is
   the only cluster in the account. AWS specifies paginated cluster results in
   [`ListClusters`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ListClusters.html).
3. For each cluster, paginate `ecs:ListTasks` twice with desired status
   `RUNNING` and `STOPPED`, then union the ARNs. `RUNNING` is the desired-status
   filter, while recently stopped tasks can still be returned; collecting both
   allows the audit to retain tasks whose desired state is stopped but whose
   last state is still transitional. See
   [`ListTasks`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ListTasks.html)
   and the [ECS task lifecycle](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-lifecycle-explanation.html).
4. Call `ecs:DescribeTasks` in batches of at most 100. Retain every task whose
   `lastStatus` is not `STOPPED` or `DELETED`, recording
   `taskDefinitionArn`, each container's exact repository from `image`, and
   `imageDigest`. AWS defines the batch limit and these response fields in
   [`DescribeTasks`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeTasks.html);
   `imageDigest` is the container image manifest digest in the
   [`Container` API](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Container.html).
5. Map only exact repository URIs for `edgartools-prod-warehouse` and
   `edgartools-prod-mdm`. Sidecars or external images are recorded but excluded
   from these two repositories. A runtime digest that cannot be found in the
   expected repository aborts cleanup rather than being ignored.

This is stricter than the existing cleanup script's “latest active revision per
family” scan. That shortcut neither enumerates running-task digests nor all
active revisions, so it is not deletion-grade evidence.

## Task-definition retirement

Before deregistration, build a complete set of task-definition ARNs from:

- all three verified deployment cohorts;
- every active `edgartools-prod*` Step Functions definition, including nested
  Map/Parallel branches containing `TaskDefinition` parameters;
- all ECS services, deployments, and task sets in every cluster;
- every live or transitioning task found above; and
- all `ACTIVE` task definitions with the `edgartools-prod` family prefix.

Describe every active revision, not only the latest revision per family. Resolve
each production ECR image reference to a digest. A tag-only reference is mutable
and ambiguous unless its currently resolved digest is recorded; treat it as a
blocker and migrate the retained definition to a digest-pinned revision.

An active revision is stale only if it is absent from the cohort, workflow,
service/deployment/task-set, and task reference sets. Deregister those revisions,
then repeat the entire enumeration and require them to report `INACTIVE` before
their digests can enter a delete plan. Permanent `DeleteTaskDefinitions` can be
a later metadata cleanup: AWS states that deregistration already prevents new
launches and does not disturb existing tasks, while deletion may remain
`DELETE_IN_PROGRESS` until ECS dependencies disappear.

## Lifecycle-policy boundary

For the final warehouse and MDM repositories, keep lifecycle automation scoped
to untagged leftovers, for example:

```json
{
  "rules": [
    {
      "rulePriority": 1,
      "description": "Expire untagged build leftovers after one day",
      "selection": {
        "tagStatus": "untagged",
        "countType": "sinceImagePushed",
        "countUnit": "days",
        "countNumber": 1
      },
      "action": {"type": "expire"}
    }
  ]
}
```

Run `StartLifecyclePolicyPreview`, wait for `COMPLETE`, paginate every
`GetLifecyclePolicyPreview` result, and require that every `EXPIRE` result is
untagged and outside the protected digest set before applying the policy. AWS
calls preview a best practice and documents that matching images may expire
within 24 hours; see
[Creating a lifecycle-policy preview](https://docs.aws.amazon.com/AmazonECR/latest/userguide/lpp_creation.html)
and [`GetLifecyclePolicyPreview`](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_GetLifecyclePolicyPreview.html).

Do not add a tagged `sha-*` or `tagStatus: any` count rule. A protected image
normally also has an immutable `sha-*` tag, so a broad tagged rule can select it.
Count selection follows push time rather than the verified cohort order. A
high-priority expiration rule should not be repurposed as a synthetic “keep”
rule; ECR supports only `expire` (and archive-related) actions, making that
contract unnecessarily dependent on rule-conflict side effects.

Tagged stale final images are removed by the audited reconciler, not lifecycle
age/count. `BatchDeleteImage` by digest deletes the image and all its tags;
deleting by tag removes that tag, and removing the final tag deletes the image.
Therefore “untag now, let lifecycle delete later” does **not** provide a grace
period when the last tag is removed. See
[`BatchDeleteImage`](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_BatchDeleteImage.html).

## Dry-run and apply contract

The cleanup tool must default to dry-run and emit a canonical JSON plan with:

- account, Region, repository, audit start time, and a plan SHA-256;
- complete image inventory: digest, all tags, push time, size, and disposition;
- protected-set provenance per digest (`current`, `rollback-1`, `rollback-2`,
  `active_task_definition`, `workflow`, `service`, or `live_task`);
- stale task-definition revisions proposed for deregistration;
- candidate image digests and expected reclaimed bytes; and
- all AWS pagination counts and an empty error/failure list.

Apply requires the exact plan hash. It acquires a production cleanup/deployment
lock, repeats every AWS read, and aborts if identity, registry version, ECR
inventory, tags, task/task-definition/workflow references, or candidates differ.
It deregisters stale task definitions first, repeats reconciliation again, and
only then deletes exact candidate digests in bounded batches. Any partial ECR
failure aborts further batches and is reported. The current deploy script's
non-fatal cleanup behavior is incompatible with this contract: cleanup errors
must not be swallowed when an apply was requested.

The implementation should also refuse to delete images pushed after the audit
started. This prevents a concurrent or newly published candidate from entering
an older cleanup plan even before lock enforcement.

## Repository scope

| Repository class | Repositories | Contract |
| --- | --- | --- |
| Runtime final images | `edgartools-prod-warehouse`, `edgartools-prod-mdm` | Deployment-cohort registry, ECR mirror tags, ECS/Step Functions reconciliation, task-definition retirement, hash-bound delete plan, untagged-only lifecycle policy. |
| Build dependency images | `edgartools-prod-warehouse-deps`, `edgartools-prod-mdm-deps` | Separate build-cache policy. They are not ECS task images and must not be added to the runtime rollback registry. Retain the current explicitly referenced dependency tag plus one previous dependency tag (or the repo's documented build-cache set), protect any in-progress build under the deployment lock, and use a separate previewed count policy. |

The two final repositories must be handled consistently, but their protected
digests are resolved independently inside the same deployment cohort. Dependency
repositories are excluded from runtime task-reference claims; deleting an old
dependency tag must never be presented as deleting an executable rollback image.

## Fail-closed conditions

No tagged final image deletion is allowed when any of the following is true:

- the production identity or Region is wrong;
- the cohort registry is missing, malformed, unversioned, lacks verification
  evidence, has ambiguous ordering, or disagrees with ECR mirror tags;
- fewer than three verified cohorts exist without an explicit retain-all
  disposition;
- a protected digest or immutable tag is missing from ECR;
- any AWS listing is unpaginated, errors, or returns unresolved failures;
- a live container lacks `imageDigest`, or a production image reference cannot
  be resolved exactly;
- an active task definition is tag-pinned, uncategorized, or still references a
  candidate digest;
- a Step Functions definition, ECS service/deployment/task set, or live task
  references the candidate revision/digest;
- stale task definitions have not been observed as `INACTIVE` in the repeated
  audit;
- lifecycle preview includes a tagged or protected digest;
- the apply-time inventory differs from the dry-run plan;
- a deployment/build lock cannot be acquired; or
- any candidate was pushed after the audit began.

## Local implementation implications

- `infra/scripts/cleanup-ecr-images.sh` currently keeps every tagged final image,
  scans only the latest active task-definition revision per family, does not
  enumerate running tasks, and deletes by digest. It must be replaced or made
  to implement the contract above; `--keep-sha` is not verified rollback
  selection.
- `infra/scripts/deploy-aws-application.sh` invokes cleanup with `--apply` but
  converts failure into a non-fatal log message. Destructive cleanup must become
  an explicit, fail-closed phase and must not race image publication.
- `infra/terraform/modules/warehouse_runtime/main.tf` already uses an
  untagged-only warehouse policy, which is the correct safety boundary, but the
  “newest 20” value does not control tagged growth. MDM final and both dependency
  repositories need explicit ownership and policies consistent with their
  separate contracts.

## Primary sources

- [Amazon ECR lifecycle policies](https://docs.aws.amazon.com/AmazonECR/latest/userguide/LifecyclePolicies.html)
- [Amazon ECR lifecycle-policy properties](https://docs.aws.amazon.com/AmazonECR/latest/userguide/lifecycle_policy_parameters.html)
- [Amazon ECR lifecycle-policy preview](https://docs.aws.amazon.com/AmazonECR/latest/userguide/lpp_creation.html)
- [Amazon ECR `GetLifecyclePolicyPreview`](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_GetLifecyclePolicyPreview.html)
- [Amazon ECR `BatchDeleteImage`](https://docs.aws.amazon.com/AmazonECR/latest/APIReference/API_BatchDeleteImage.html)
- [Amazon ECR image retagging](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-retag.html)
- [Amazon ECS `ListTasks`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_ListTasks.html)
- [Amazon ECS `DescribeTasks`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_DescribeTasks.html)
- [Amazon ECS `Container`](https://docs.aws.amazon.com/AmazonECS/latest/APIReference/API_Container.html)
- [Amazon ECS task lifecycle](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-lifecycle-explanation.html)
- [Amazon ECS task-definition states](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-definition-state.html)
- [AWS Step Functions ECS integration](https://docs.aws.amazon.com/step-functions/latest/dg/connect-ecs.html)
- [AWS Step Functions `DescribeStateMachine`](https://docs.aws.amazon.com/step-functions/latest/APIReference/API_DescribeStateMachine.html)
