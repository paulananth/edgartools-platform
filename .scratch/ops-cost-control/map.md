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
- [Attribute Production Log Volume by Event Family](issues/01-attribute-production-log-volume.md) — measured a bounded 14-hour representative execution (1.3M records/206MB scanned via Logs Insights). Largest contributor by far (61.9M bytes, 71% of all records) is not a logging-design problem but a diagnostic bug: `warehouse_orchestrator.py:265` and `command_runner.py:39` both pretty-print the full command result payload (including every document's write receipt) to stdout at the end of every invocation. Second tier is legitimate but high-cardinality per-record SEC-call/fetch events (~100M bytes). Stage summaries and failures are already negligible. Also found current CloudWatch retention is live at 30 days, not the 7 days the map's Notes claimed — flagged for ticket 03.
- [Replace Routine Per-Record Logs with Bounded Summaries](issues/02-replace-routine-record-logs-with-summaries.md) — implemented and tested (not yet deployed): bounded the `raw_writes` field in printed command results to a 5-entry sample (`_command_result_for_log`/`_print_command_result`, `warehouse_orchestrator.py`), used by both `run_command` and `execute_standard_command`. Confirmed zero information loss — the full list is already durable in `pipeline_run.raw_writes_json` and the underlying bronze S3 objects. Deliberately did not touch the second-tier per-record SEC-call/fetch events (finding 2): they're not duplicated elsewhere, this repo has relied on them to root-cause a real incident, and their right aggregation boundary is still an open, undecided question — left in the fog rather than decided by fiat inside a task ticket.
- [Make Seven-Day Production Log Retention Durable](issues/03-make-seven-day-log-retention-durable.md) — root cause was two independent 30-day hardcodes (Terraform's `aws_cloudwatch_log_group.ecs` and the deploy script's `ensure_log_group()`), each silently reverting the 2026-08-01 change on every `terraform apply`/`deploy-aws-application.sh` run. Also found a third, previously-unknown gap: the Container Insights performance log group is AWS-auto-created and nothing asserted its retention at all. Fixed all three (code changed to require retention explicitly, no silent default), applied live immediately, verified all three `edgartools-prod` groups at 7 days, and added drift regression tests. Not yet committed.
- [Implement Bounded ECR Retention with Rollback Safety](issues/05-implement-bounded-ecr-retention.md) — corrected ticket 04's stale two-repository premise (this platform now shares one `edgartools-<env>-images` repo, tag-prefix-scoped). Given actual current risk was low (existing script never deletes tagged images; ~$1/month exposure), put the scope choice to the user rather than deciding unilaterally — user chose the full fail-closed contract. Built a durable cohort registry, a pure fail-closed reconciliation/plan engine (protected-digest computation across the registry, ECS task definitions, Step Functions, live tasks; hash-bound dry-run/apply), and a thin CLI shell reusing this repo's existing ETag-guarded staged/promote pattern for registry writes. Deliberately kept separate from the automatic per-deploy cleanup call (which stays untagged-only). 47 new tests, one real bug caught by them (a self-referential staleness check that would have never flagged anything stale). Not yet run live against AWS or committed.

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
