# Production Observability and Image Cost Control

Label: `wayfinder:map`

## Destination

Reduce production CloudWatch ingestion/storage and ECR storage growth while
preserving seven days of operational forensics, durable release evidence, the
currently running images, and an explicit two-image rollback capability.

## Notes

- **This map carries execution.** The user fixed the policy boundaries during
  grilling; tickets measure, implement, and verify them.
- AWS scope is account `690839588395`, region `us-east-1`, and resources named
  `edgartools-prod`. Re-verify identity and exact resource scope before changes.
- The **Operational Forensics Window** is seven days for all three production
  CloudWatch log groups. On 2026-08-01 their live policies were changed from
  30 days (one Container Insights group was already one day) to seven days;
  older events are pending retention-driven deletion.
- The **Rollback Image Set** is the current production digest, the two most
  recent verified successful rollback digests, and any digest referenced by a
  currently running ECS task.
- Live baseline: the ECS execution group stored 732,476,026 bytes, the Step
  Functions group 12,045,337 bytes, and Container Insights 557,657 bytes. The
  warehouse ECR repository held ten tagged images totaling about 2.8 GiB.
- Current workflow definitions reference warehouse digest
  `sha256:6c3241170918bcece71fe3156c7d8e58ba15f4dd7fd0c7936abd6f9273878fd6`.
- Before code changes use `/gof-refactor-reviewer`; then use `/tdd` and
  `/code-review`. Do not force a pattern merely to aggregate logs.
- Cleanup must be audit-first and fail closed. A lifecycle policy or cleanup
  script may not delete a digest until running-task and explicit rollback
  references have been reconciled.

## Decisions so far

<!-- Closed ticket decisions: one-line gist and link; detail stays in the ticket. -->

- [Confirm a Safe ECR Rollback-Protection Mechanism](issues/04-confirm-safe-ecr-rollback-protection-mechanism.md) — Use a durable three-cohort registry and fail-closed ECS/workflow reconciliation; lifecycle remains untagged-only and cannot decide tagged rollback safety.

## Not yet specified

- Which structured event families dominate ingested ECS log bytes and whether
  their summaries should be per stage, batch, accession disposition, or bounded
  time window. The production baseline must determine that boundary.
- Whether seven days of lower-volume logs produces enough savings to justify
  changing Step Functions logging level as well. Do not change it without a
  measured contributor.

## Out of scope

- Deleting durable run manifests, release evidence, Bronze artifacts, or data
  needed for long-lived integrity and audit claims.
- Reducing log retention below seven days or selectively retaining errors past
  seven days in CloudWatch; durable evidence must carry longer-lived facts.
- Deleting ECR images merely because they are old, untagged, or absent from the
  latest workflow definition without reconciling running and rollback use.
- Changing image contents, build layering, or base-image architecture solely
  to reduce repository size in this effort.
